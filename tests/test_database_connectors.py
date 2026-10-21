from unittest.mock import Mock

import pytest

import database_connectors as connectors
from database_connectors import (
    DatabaseConnectionError,
    TableRef,
    import_table,
    list_tables,
)


def _response(status_code, payload):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


def test_table_reference_label_includes_schema():
    assert TableRef("orders", "public").label == "public.orders"
    assert TableRef("orders").label == "orders"


def test_supabase_table_listing_returns_only_get_endpoints(monkeypatch):
    request = Mock(return_value=_response(
        200,
        {
            "paths": {
                "/customers": {"get": {}},
                "/rpc/report": {"post": {}},
                "/orders": {"get": {}, "post": {}},
                "/nested/path": {"get": {}},
            }
        },
    ))
    monkeypatch.setattr(connectors.requests, "get", request)

    tables = list_tables({
        "provider": "Supabase",
        "url": "https://project.supabase.co",
        "key": "anon-key",
    })

    assert [table.name for table in tables] == ["customers", "orders"]
    assert request.call_args.kwargs["headers"]["apikey"] == "anon-key"
    assert request.call_args.kwargs["timeout"] == 10


def test_supabase_connector_rejects_non_supabase_hosts():
    with pytest.raises(DatabaseConnectionError, match="Supabase project URL"):
        list_tables({
            "provider": "Supabase",
            "url": "https://internal.example.com",
            "key": "secret",
        })


def test_supabase_connector_rejects_service_role_key():
    with pytest.raises(DatabaseConnectionError, match="Service-role keys are blocked"):
        list_tables({
            "provider": "Supabase",
            "url": "https://project.supabase.co",
            "key": "sb_secret_project-key",
        })


def test_production_database_connections_reject_private_networks(monkeypatch):
    monkeypatch.setattr(connectors.settings, "app_env", "production")

    with pytest.raises(DatabaseConnectionError, match="public database host"):
        connectors._validate_public_host("localhost", 5432)
    with pytest.raises(DatabaseConnectionError, match="private, local, or reserved"):
        connectors._validate_public_host("127.0.0.1", 5432)


def test_production_database_host_allows_public_addresses(monkeypatch):
    monkeypatch.setattr(connectors.settings, "app_env", "production")
    monkeypatch.setattr(
        connectors.socket,
        "getaddrinfo",
        Mock(return_value=[(2, 1, 6, "", ("8.8.8.8", 5432))]),
    )

    connectors._validate_public_host("db.example.com", 5432)


def test_mongodb_uri_cannot_disable_tls_verification():
    with pytest.raises(DatabaseConnectionError, match="disabled TLS certificate verification"):
        connectors._mongo_collection({
            "provider": "MongoDB",
            "uri": "mongodb://example.com/?tlsAllowInvalidCertificates=true",
            "database": "analytics",
        })


def test_production_mongodb_connections_reject_private_hosts(monkeypatch):
    monkeypatch.setattr(connectors.settings, "app_env", "production")

    with pytest.raises(DatabaseConnectionError, match="private, local, or reserved"):
        connectors._mongo_collection({
            "provider": "MongoDB",
            "uri": "mongodb://127.0.0.1:27017",
            "database": "analytics",
        })


def test_supabase_import_applies_shared_dataframe_validation(monkeypatch):
    monkeypatch.setattr(
        connectors.requests,
        "get",
        Mock(return_value=_response(
            200,
            [{"Revenue": 10}, {"Revenue": 20}],
        )),
    )

    dataset = import_table(
        {
            "provider": "Supabase",
            "url": "https://project.supabase.co",
            "key": "anon-key",
        },
        TableRef("sales"),
    )

    assert dataset.filename == "sales"
    assert dataset.file_format == "Supabase"
    assert dataset.row_count == 2
    assert dataset.column_names == ["Revenue"]


def test_supabase_import_rejects_row_limit_excess(monkeypatch):
    monkeypatch.setattr(connectors.settings, "max_rows", 1)
    monkeypatch.setattr(
        connectors.requests,
        "get",
        Mock(return_value=_response(
            200,
            [{"id": 1}, {"id": 2}],
        )),
    )

    with pytest.raises(DatabaseConnectionError, match="row import limit"):
        import_table(
            {
                "provider": "Supabase",
                "url": "https://project.supabase.co",
                "key": "anon-key",
            },
            TableRef("records"),
        )


def test_supabase_request_errors_do_not_echo_credentials(monkeypatch):
    monkeypatch.setattr(
        connectors.requests,
        "get",
        Mock(return_value=_response(403, {"message": "permission denied"})),
    )

    with pytest.raises(DatabaseConnectionError) as error:
        list_tables({
            "provider": "Supabase",
            "url": "https://project.supabase.co",
            "key": "secret-key",
        })

    assert "secret-key" not in str(error.value)
