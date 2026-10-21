"""Server-to-server client for the protected FastAPI application backend."""

from __future__ import annotations

from typing import Any

import requests

from config import settings


class BackendApiError(ValueError):
    """A safe message returned from or raised while calling the API backend."""


class BackendApiClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
    ):
        self.base_url = (base_url or settings.app_api_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.app_api_key

    def _request(
        self,
        method: str,
        path: str,
        *,
        timeout: int = 20,
        access_token: str = "",
        refresh_token: str = "",
        **kwargs: Any,
    ) -> Any:
        if len(self.api_key.strip()) < 32:
            raise BackendApiError(
                "FastAPI is not configured. Set APP_API_URL and an APP_API_KEY "
                "of at least 32 characters in the frontend environment."
            )
        headers = dict(kwargs.pop("headers", {}))
        headers["X-App-API-Key"] = self.api_key
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        if refresh_token:
            headers["X-Refresh-Token"] = refresh_token
        try:
            response = requests.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                timeout=timeout,
                **kwargs,
            )
        except requests.RequestException:
            raise BackendApiError(
                "Could not reach the FastAPI backend. Start it and check APP_API_URL."
            ) from None
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", "Request failed.")
            except (ValueError, AttributeError):
                detail = "Request failed."
            raise BackendApiError(
                f"Backend request failed ({response.status_code}): {str(detail)[:300]}"
            )
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            raise BackendApiError("The FastAPI backend returned invalid JSON.") from None

    def sign_up(self, email: str, password: str) -> dict:
        return self._request(
            "POST",
            "/api/auth/signup",
            json={"email": email, "password": password},
        )

    def auth_status(self) -> bool:
        result = self._request("GET", "/api/auth/status")
        return bool(result["configured"])

    def sign_in(self, email: str, password: str) -> dict:
        return self._request(
            "POST",
            "/api/auth/login",
            json={"email": email, "password": password},
        )

    def sign_out(self, access_token: str, refresh_token: str = "") -> None:
        self._request(
            "POST",
            "/api/auth/logout",
            access_token=access_token,
            refresh_token=refresh_token,
        )

    def list_history(self, access_token: str, refresh_token: str = "") -> dict:
        return self._request(
            "GET",
            "/api/history",
            access_token=access_token,
            refresh_token=refresh_token,
        )

    def save_history(
        self,
        access_token: str,
        title: str,
        question: str,
        answer: str,
        refresh_token: str = "",
    ) -> dict:
        return self._request(
            "POST",
            "/api/history",
            access_token=access_token,
            refresh_token=refresh_token,
            json={"title": title, "question": question, "answer": answer},
        )

    def list_database_tables(self, connection: dict) -> list[dict]:
        result = self._request(
            "POST",
            "/api/database/tables",
            timeout=30,
            json=connection,
        )
        return result["tables"]

    def import_database_table(
        self, connection: dict, table: dict
    ) -> dict:
        return self._request(
            "POST",
            "/api/database/import",
            timeout=120,
            json={
                "connection": connection,
                "table": table["name"],
                "schema": table.get("schema"),
            },
        )
