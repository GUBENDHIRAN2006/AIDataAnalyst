"""Protected FastAPI boundary for Supabase auth/history and database imports."""

from __future__ import annotations

import hmac
import hashlib
import json
import logging
import threading
import time
from collections import defaultdict
from typing import Literal

import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from agent import run_agent
from config import settings
from database_connectors import (
    DatabaseConnectionError,
    TableRef,
    import_table,
    list_tables,
)
from data_loader import DataLoaderError, load_records
from user_services import (
    SupabaseUserService,
    UserServiceError,
    is_supabase_service_role_key,
    is_valid_supabase_project_url,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Data Analyst API",
    description="Internal API for account, history, and data-source operations.",
    version="1.0.0",
    docs_url=None if settings.app_env == "production" else "/docs",
    redoc_url=None,
)

_RATE_WINDOW_SECONDS = 60
_AUTH_REQUESTS_PER_WINDOW = 10
_rate_limit_state: dict[tuple[str, str, str], tuple[int, int]] = {}
_rate_limit_lock = threading.Lock()


class AuthPayload(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class DatabasePayload(BaseModel):
    provider: Literal["PostgreSQL", "MySQL", "MongoDB", "Supabase"]
    host: str | None = Field(default=None, max_length=253)
    port: int | None = Field(default=None, ge=1, le=65535)
    database: str | None = Field(default=None, max_length=256)
    username: str | None = Field(default=None, max_length=256)
    password: str | None = Field(default=None, max_length=4096)
    uri: str | None = Field(default=None, max_length=4096)
    url: str | None = Field(default=None, max_length=512)
    key: str | None = Field(default=None, max_length=4096)
    access_token: str | None = Field(default=None, max_length=8192)
    ssl: bool = True

    def connector_config(self) -> dict:
        return self.model_dump(exclude_none=True)


class ImportPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    connection: DatabasePayload
    table: str = Field(min_length=1, max_length=512)
    table_schema: str | None = Field(default=None, alias="schema", max_length=256)


class HistoryPayload(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    question: str = Field(min_length=1, max_length=4000)
    answer: str = Field(min_length=1, max_length=12000)


class AnalysisPayload(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    records: list[dict] = Field(min_length=1, max_length=500000)
    filename: str = Field(default="imported-data.csv", min_length=1, max_length=255)


def require_internal_api_key(
    x_app_api_key: str | None = Header(default=None, alias="X-App-API-Key"),
) -> None:
    configured_key = settings.app_api_key.strip()
    if len(configured_key) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="FastAPI internal authentication is not configured.",
        )
    if not x_app_api_key or not hmac.compare_digest(x_app_api_key, configured_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid application credentials.",
        )


def _check_auth_rate_limit(request: Request, action: str, email: str) -> None:
    client_host = request.client.host if request.client else "unknown"
    now = int(time.time())
    window = now // _RATE_WINDOW_SECONDS
    identity = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
    key = (client_host, action, identity)
    with _rate_limit_lock:
        if len(_rate_limit_state) > 2048:
            for entry, (entry_window, _) in list(_rate_limit_state.items()):
                if entry_window < window:
                    _rate_limit_state.pop(entry, None)
        entry_window, count = _rate_limit_state.get(key, (window, 0))
        if entry_window != window:
            count = 0
        if count >= _AUTH_REQUESTS_PER_WINDOW:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many account requests. Try again in a minute.",
            )
        _rate_limit_state[key] = (window, count + 1)


def _supabase_user_service(access_token: str = "", refresh_token: str = ""):
    if (
        not settings.has_supabase_config
        or not is_valid_supabase_project_url(settings.supabase_url)
        or is_supabase_service_role_key(settings.supabase_anon_key)
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase Auth is not configured with a safe project key.",
        )
    return SupabaseUserService(
        settings.supabase_url,
        settings.supabase_anon_key,
        access_token=access_token,
        refresh_token=refresh_token,
    )


def _authorization_tokens(
    authorization: str | None, refresh_token: str | None
) -> tuple[str, str]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to access this account resource.",
        )
    return authorization[7:].strip(), (refresh_token or "").strip()


def _map_user_service_error(exc: UserServiceError) -> HTTPException:
    message = str(exc)
    if "401" in message or "403" in message:
        code = status.HTTP_401_UNAUTHORIZED
    elif "429" in message:
        code = status.HTTP_429_TOO_MANY_REQUESTS
    elif "Supabase request failed (5" in message:
        code = status.HTTP_502_BAD_GATEWAY
    else:
        code = status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=code, detail=message)


def _auth_result(service: SupabaseUserService, result: dict) -> dict:
    user = result.get("user") or {}
    return {
        "user": {
            "id": user.get("id", ""),
            "email": user.get("email", ""),
        },
        "access_token": service.access_token,
        "refresh_token": service.refresh_token,
        "requires_email_confirmation": not bool(service.access_token),
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get(
    "/api/auth/status",
    dependencies=[Depends(require_internal_api_key)],
)
def auth_status():
    configured = (
        settings.has_supabase_config
        and is_valid_supabase_project_url(settings.supabase_url)
        and not is_supabase_service_role_key(settings.supabase_anon_key)
    )
    return {"configured": configured}


@app.post("/api/auth/signup", dependencies=[Depends(require_internal_api_key)])
def sign_up(payload: AuthPayload, request: Request):
    _check_auth_rate_limit(request, "signup", payload.email)
    if len(payload.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Use a password with at least 8 characters.",
        )
    try:
        service = _supabase_user_service()
        result = service.sign_up(payload.email.strip().lower(), payload.password)
        return _auth_result(service, result)
    except UserServiceError as exc:
        raise _map_user_service_error(exc) from None


@app.post("/api/auth/login", dependencies=[Depends(require_internal_api_key)])
def sign_in(payload: AuthPayload, request: Request):
    _check_auth_rate_limit(request, "login", payload.email)
    try:
        service = _supabase_user_service()
        result = service.sign_in(payload.email.strip().lower(), payload.password)
        response = _auth_result(service, result)
        if not service.access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Confirm your email address before signing in.",
            )
        return response
    except UserServiceError as exc:
        raise _map_user_service_error(exc) from None


@app.post("/api/auth/logout", dependencies=[Depends(require_internal_api_key)])
def sign_out(
    authorization: str | None = Header(default=None),
    refresh_token: str | None = Header(default=None, alias="X-Refresh-Token"),
):
    access_token, refresh = _authorization_tokens(authorization, refresh_token)
    try:
        service = _supabase_user_service(
            access_token=access_token, refresh_token=refresh
        )
        service.sign_out()
        return {"signed_out": True}
    except UserServiceError as exc:
        raise _map_user_service_error(exc) from None


@app.get("/api/history", dependencies=[Depends(require_internal_api_key)])
def get_history(
    authorization: str | None = Header(default=None),
    refresh_token: str | None = Header(default=None, alias="X-Refresh-Token"),
):
    access_token, refresh = _authorization_tokens(authorization, refresh_token)
    try:
        service = _supabase_user_service(
            access_token=access_token, refresh_token=refresh
        )
        entries = service.list_history()
        return {
            "items": entries,
            "access_token": service.access_token,
            "refresh_token": service.refresh_token,
        }
    except UserServiceError as exc:
        raise _map_user_service_error(exc) from None


@app.post("/api/history", dependencies=[Depends(require_internal_api_key)])
def save_history(
    payload: HistoryPayload,
    authorization: str | None = Header(default=None),
    refresh_token: str | None = Header(default=None, alias="X-Refresh-Token"),
):
    access_token, refresh = _authorization_tokens(authorization, refresh_token)
    try:
        service = _supabase_user_service(
            access_token=access_token, refresh_token=refresh
        )
        service.save_history(payload.title, payload.question, payload.answer)
        return {
            "saved": True,
            "access_token": service.access_token,
            "refresh_token": service.refresh_token,
        }
    except UserServiceError as exc:
        raise _map_user_service_error(exc) from None


@app.post(
    "/api/database/tables",
    dependencies=[Depends(require_internal_api_key)],
)
def get_database_tables(payload: DatabasePayload):
    try:
        tables = list_tables(payload.connector_config())
        return {"tables": [{"name": table.name, "schema": table.schema} for table in tables]}
    except DatabaseConnectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@app.post(
    "/api/database/import",
    dependencies=[Depends(require_internal_api_key)],
)
def import_database_table(payload: ImportPayload):
    try:
        dataset = import_table(
            payload.connection.connector_config(),
            TableRef(name=payload.table, schema=payload.table_schema),
        )
        records_json = dataset.df.to_json(
            orient="records",
            date_format="iso",
            date_unit="ms",
        )
        if len(records_json.encode("utf-8")) > settings.max_upload_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=(
                    "The imported data exceeds the configured transfer-size limit. "
                    "Choose a smaller table or reduce MAX_UPLOAD_SIZE_MB."
                ),
            )
        return {
            "filename": dataset.filename,
            "file_format": dataset.file_format,
            "file_size_bytes": dataset.file_size_bytes,
            "encoding_detected": dataset.encoding_detected,
            "warnings": dataset.warnings,
            "records": json.loads(records_json),
        }
    except DatabaseConnectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@app.post(
    "/api/analyze",
    dependencies=[Depends(require_internal_api_key)],
)
def analyze_records(
    payload: AnalysisPayload,
    authorization: str | None = Header(default=None),
    refresh_token: str | None = Header(default=None, alias="X-Refresh-Token"),
):
    serialized_records = json.dumps(payload.records, separators=(",", ":"), default=str)
    if len(serialized_records.encode("utf-8")) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="The dataset exceeds the configured transfer-size limit.",
        )
    try:
        dataset = load_records(
            payload.records,
            filename=payload.filename,
            file_format="database",
            file_size_bytes=len(serialized_records.encode("utf-8")),
        )
        result = run_agent(payload.question, dataset)
        response = result.to_dict()
        if authorization and authorization.startswith("Bearer ") and response.get("answer"):
            service = _supabase_user_service(
                access_token=authorization[7:].strip(),
                refresh_token=(refresh_token or "").strip(),
            )
            service.save_history(
                payload.question[:120],
                payload.question,
                response["answer"][:12000],
            )
            response["access_token"] = service.access_token
            response["refresh_token"] = service.refresh_token
        return response
    except DataLoaderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except UserServiceError as exc:
        raise _map_user_service_error(exc) from None
