from unittest.mock import Mock

import pytest

from user_services import (
    SupabaseUserService,
    UserServiceError,
    is_valid_supabase_project_url,
    is_supabase_service_role_key,
)


def _response(status_code, payload):
    response = Mock()
    response.status_code = status_code
    response.content = b"{}"
    response.json.return_value = payload
    return response


def test_supabase_url_validation_requires_https_project_host():
    assert is_valid_supabase_project_url("https://project-123.supabase.co")
    assert not is_valid_supabase_project_url("http://project.supabase.co")
    assert not is_valid_supabase_project_url("https://localhost")
    assert not is_valid_supabase_project_url("https://evil.supabase.co.example.com")
    assert not is_valid_supabase_project_url("https://user:pass@project.supabase.co")


def test_service_role_keys_are_detected_and_publishable_keys_are_accepted():
    assert is_supabase_service_role_key("sb_secret_project-key")
    assert not is_supabase_service_role_key("sb_publishable_project-key")
    assert not is_supabase_service_role_key("eyJhbGciOiJub25lIn0.eyJyb2xlIjoiYW5vbiJ9.signature")


def test_signup_rejects_short_password_without_network_call(monkeypatch):
    request = Mock()
    monkeypatch.setattr("user_services.requests.request", request)
    service = SupabaseUserService("https://project.supabase.co", "anon-key")

    with pytest.raises(UserServiceError, match="8 characters"):
        service.sign_up("user@example.com", "short")

    request.assert_not_called()


def test_sign_in_stores_session_tokens(monkeypatch):
    monkeypatch.setattr(
        "user_services.requests.request",
        Mock(return_value=_response(
            200,
            {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "user": {"id": "user-id", "email": "user@example.com"},
            },
        )),
    )
    service = SupabaseUserService("https://project.supabase.co", "anon-key")

    result = service.sign_in(" user@example.com ", "a-long-password")

    assert result["user"]["id"] == "user-id"
    assert service.access_token == "access-token"
    assert service.refresh_token == "refresh-token"


def test_get_user_uses_authenticated_supabase_endpoint(monkeypatch):
    request = Mock(return_value=_response(
        200,
        {"id": "user-id", "email": "admin@example.com"},
    ))
    monkeypatch.setattr("user_services.requests.request", request)
    service = SupabaseUserService(
        "https://project.supabase.co",
        "anon-key",
        "access-token",
        "refresh-token",
    )

    assert service.get_user() == {
        "id": "user-id",
        "email": "admin@example.com",
    }
    assert request.call_args.args == ("GET", "https://project.supabase.co/auth/v1/user")
    assert request.call_args.kwargs["headers"]["Authorization"] == "Bearer access-token"


def test_expired_access_token_is_refreshed_and_history_is_user_scoped(monkeypatch):
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if len(calls) == 1:
            return _response(401, {"message": "expired"})
        if "/auth/v1/token?" in url:
            return _response(
                200,
                {"access_token": "new-access", "refresh_token": "new-refresh"},
            )
        if url.endswith("/auth/v1/user"):
            return _response(
                200,
                {"id": "user-123", "email": "one@example.com"},
            )
        return _response(200, [{"id": "entry-1"}])

    monkeypatch.setattr("user_services.requests.request", request)
    service = SupabaseUserService(
        "https://project.supabase.co",
        "anon-key",
        "expired-access",
        "refresh-token",
    )

    history = service.list_history()

    assert history == [{"id": "entry-1"}]
    assert service.access_token == "new-access"
    assert service.refresh_token == "new-refresh"
    assert calls[-1][2]["headers"]["Authorization"] == "Bearer new-access"
    assert calls[-1][2]["params"]["user_id"] == "eq.user-123"


def test_history_insert_sets_verified_user_id_and_uses_authenticated_token(monkeypatch):
    request = Mock(side_effect=[
        _response(200, {"id": "user-123", "email": "one@example.com"}),
        _response(201, {}),
    ])
    monkeypatch.setattr("user_services.requests.request", request)
    service = SupabaseUserService(
        "https://project.supabase.co", "anon-key", "user-access", "user-refresh"
    )

    service.save_history("Revenue total", "What is revenue?", "Total is 42.")

    args, kwargs = request.call_args_list[-1]
    assert args[0] == "POST"
    assert args[1].endswith("/rest/v1/analysis_history")
    assert kwargs["headers"]["Authorization"] == "Bearer user-access"
    assert kwargs["json"] == {
        "user_id": "user-123",
        "title": "Revenue total",
        "question": "What is revenue?",
        "answer": "Total is 42.",
    }
