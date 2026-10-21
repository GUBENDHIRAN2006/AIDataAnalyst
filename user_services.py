"""Supabase Auth and row-level-secured analysis history."""

from __future__ import annotations

import base64
import json
from typing import Any

import requests


class UserServiceError(ValueError):
    """A safe, user-facing authentication or history error."""


def is_supabase_service_role_key(key: str) -> bool:
    if key.strip().startswith("sb_secret_"):
        return True
    parts = key.strip().split(".")
    if len(parts) != 3:
        return False
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
        return json.loads(decoded).get("role") == "service_role"
    except (ValueError, UnicodeError, json.JSONDecodeError):
        return False


class SupabaseUserService:
    def __init__(
        self,
        project_url: str,
        anon_key: str,
        access_token: str = "",
        refresh_token: str = "",
    ):
        self.project_url = project_url.rstrip("/")
        self.anon_key = anon_key
        self.access_token = access_token
        self.refresh_token = refresh_token

    def _request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = False,
        retry_refresh: bool = True,
        **kwargs: Any,
    ) -> Any:
        headers = dict(kwargs.pop("headers", {}))
        headers["apikey"] = self.anon_key
        if authenticated and self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        try:
            response = requests.request(
                method,
                f"{self.project_url}{path}",
                headers=headers,
                timeout=15,
                **kwargs,
            )
        except requests.RequestException:
            raise UserServiceError(
                "Could not reach Supabase. Check the app's Supabase configuration "
                "and network connection."
            ) from None

        if (
            response.status_code == 401
            and authenticated
            and retry_refresh
            and self.refresh_token
            and path != "/auth/v1/token?grant_type=refresh_token"
        ):
            self._refresh_session()
            return self._request(
                method,
                path,
                authenticated=True,
                retry_refresh=False,
                headers=headers,
                **kwargs,
            )

        if response.status_code >= 400:
            try:
                body = response.json()
            except ValueError:
                body = {}
            if not isinstance(body, dict):
                body = {}
            message = (
                body.get("msg")
                or body.get("message")
                or body.get("error_description")
                or "Request failed."
            )
            raise UserServiceError(
                f"Supabase request failed ({response.status_code}): "
                f"{str(message)[:240]}"
            )
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            raise UserServiceError("Supabase returned an invalid response.") from None

    def _set_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = payload.get("session") or payload
        self.access_token = session.get("access_token", "")
        self.refresh_token = session.get("refresh_token", "")
        return payload

    def sign_up(self, email: str, password: str) -> dict[str, Any]:
        if len(password) < 8:
            raise UserServiceError("Use a password with at least 8 characters.")
        payload = self._request(
            "POST",
            "/auth/v1/signup",
            json={"email": email.strip(), "password": password},
        )
        return self._set_session(payload)

    def sign_in(self, email: str, password: str) -> dict[str, Any]:
        payload = self._request(
            "POST",
            "/auth/v1/token?grant_type=password",
            json={"email": email.strip(), "password": password},
        )
        return self._set_session(payload)

    def _refresh_session(self) -> None:
        payload = self._request(
            "POST",
            "/auth/v1/token?grant_type=refresh_token",
            retry_refresh=False,
            json={"refresh_token": self.refresh_token},
        )
        self._set_session(payload)
        if not self.access_token:
            raise UserServiceError("Your login session expired. Please sign in again.")

    def sign_out(self) -> None:
        if self.access_token:
            self._request("POST", "/auth/v1/logout", authenticated=True)
        self.access_token = ""
        self.refresh_token = ""

    def list_history(self, limit: int = 50) -> list[dict[str, Any]]:
        query = (
            "?select=id,title,question,answer,created_at"
            f"&order=created_at.desc&limit={max(1, min(limit, 100))}"
        )
        result = self._request(
            "GET",
            f"/rest/v1/analysis_history{query}",
            authenticated=True,
        )
        if not isinstance(result, list):
            raise UserServiceError("The history service returned an invalid response.")
        return result

    def save_history(self, title: str, question: str, answer: str) -> None:
        self._request(
            "POST",
            "/rest/v1/analysis_history",
            authenticated=True,
            headers={"Prefer": "return=minimal"},
            json={
                "title": title[:120],
                "question": question[:4000],
                "answer": answer[:12000],
            },
        )


def is_valid_supabase_project_url(project_url: str) -> bool:
    """Validate the configured Supabase URL before sending credentials."""
    from urllib.parse import urlparse

    parsed = urlparse(project_url)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.hostname.endswith(".supabase.co")
        and parsed.path in ("", "/")
        and not parsed.query
        and not parsed.fragment
        and parsed.username is None
        and parsed.password is None
    )


def normalize_email(email: str) -> str:
    return email.strip().lower()
