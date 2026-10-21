from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException
from starlette.requests import Request

import backend_api


API_KEY = "test-internal-key-" + ("x" * 40)


def _client(monkeypatch):
    monkeypatch.setattr(backend_api.settings, "app_api_key", API_KEY)
    return TestClient(backend_api.app)


def test_health_endpoint_is_available_without_internal_key():
    response = TestClient(backend_api.app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_auth_rate_limits_are_per_email_and_action():
    request = Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/auth/login",
            "raw_path": b"/api/auth/login",
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 1234),
            "server": ("testserver", 80),
        }
    )
    backend_api._rate_limit_state.clear()

    for _ in range(backend_api._AUTH_REQUESTS_PER_WINDOW):
        backend_api._check_auth_rate_limit(request, "test-login", "one@example.com")
    with pytest.raises(HTTPException) as error:
        backend_api._check_auth_rate_limit(request, "test-login", "one@example.com")
    assert error.value.status_code == 429

    backend_api._check_auth_rate_limit(request, "test-login", "two@example.com")


def test_internal_endpoints_require_the_shared_key(monkeypatch):
    client = _client(monkeypatch)

    assert client.get("/api/auth/status").status_code == 401
    assert client.get(
        "/api/auth/status",
        headers={"X-App-API-Key": "incorrect"},
    ).status_code == 401
    response = client.get(
        "/api/auth/status",
        headers={"X-App-API-Key": API_KEY},
    )

    assert response.status_code == 200
    assert response.json() == {"configured": False}


def test_auth_status_reports_valid_supabase_configuration(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(
        backend_api.settings,
        "supabase_url",
        "https://project-123.supabase.co",
    )
    monkeypatch.setattr(
        backend_api.settings,
        "supabase_anon_key",
        "sb_publishable_project-key",
    )

    response = client.get(
        "/api/auth/status",
        headers={"X-App-API-Key": API_KEY},
    )

    assert response.status_code == 200
    assert response.json() == {"configured": True}


def test_history_endpoint_forwards_user_tokens_and_returns_rotated_tokens(monkeypatch):
    client = _client(monkeypatch)
    service = SimpleNamespace(
        list_history=Mock(return_value=[{"id": "history-1"}]),
        access_token="rotated-access",
        refresh_token="rotated-refresh",
    )
    service_factory = Mock(return_value=service)
    monkeypatch.setattr(backend_api, "_supabase_user_service", service_factory)

    response = client.get(
        "/api/history",
        headers={
            "X-App-API-Key": API_KEY,
            "Authorization": "Bearer user-access",
            "X-Refresh-Token": "user-refresh",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [{"id": "history-1"}],
        "access_token": "rotated-access",
        "refresh_token": "rotated-refresh",
    }
    service_factory.assert_called_once_with(
        access_token="user-access",
        refresh_token="user-refresh",
    )


def test_history_endpoint_requires_a_user_session(monkeypatch):
    client = _client(monkeypatch)

    response = client.get(
        "/api/history",
        headers={"X-App-API-Key": API_KEY},
    )

    assert response.status_code == 401


def test_import_rejects_results_over_the_transfer_limit(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(backend_api.settings, "max_upload_size_mb", 0.000001)
    dataset = SimpleNamespace(
        df=pd.DataFrame({"value": ["a sufficiently large result"]}),
        filename="table.csv",
        file_format="csv",
        file_size_bytes=100,
        encoding_detected="utf-8",
        warnings=[],
    )
    monkeypatch.setattr(backend_api, "import_table", Mock(return_value=dataset))

    response = client.post(
        "/api/database/import",
        headers={"X-App-API-Key": API_KEY},
        json={
            "connection": {
                "provider": "PostgreSQL",
                "host": "db.example.com",
                "database": "analytics",
                "username": "reader",
                "password": "secret",
            },
            "table": "events",
        },
    )

    assert response.status_code == 413
    assert "transfer-size limit" in response.json()["detail"]


def test_analysis_endpoint_validates_records_and_returns_agent_result(monkeypatch):
    client = _client(monkeypatch)
    dataset = object()
    monkeypatch.setattr(backend_api, "load_records", Mock(return_value=dataset))
    agent_response = SimpleNamespace(
        to_dict=Mock(
            return_value={
                "answer": "Total revenue is 100.",
                "tables": [],
                "charts": [],
                "warnings": [],
                "error": None,
            }
        )
    )
    agent = Mock(return_value=agent_response)
    monkeypatch.setattr(backend_api, "run_agent", agent)

    response = client.post(
        "/api/analyze",
        headers={"X-App-API-Key": API_KEY},
        json={
            "question": "What is total revenue?",
            "filename": "sales.csv",
            "records": [{"revenue": 100}],
        },
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Total revenue is 100."
    assert "access_token" not in response.json()
    assert "refresh_token" not in response.json()
    agent.assert_called_once_with("What is total revenue?", dataset)


def test_analysis_endpoint_enforces_dataset_transfer_limit(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(backend_api.settings, "max_upload_size_mb", 0.000001)
    loader = Mock()
    monkeypatch.setattr(backend_api, "load_records", loader)

    response = client.post(
        "/api/analyze",
        headers={"X-App-API-Key": API_KEY},
        json={
            "question": "Summarize.",
            "records": [{"value": "this exceeds the small configured limit"}],
        },
    )

    assert response.status_code == 413
    loader.assert_not_called()
