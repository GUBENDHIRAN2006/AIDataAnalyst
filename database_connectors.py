"""Read-only database imports into the validated in-memory dataset model."""

from __future__ import annotations

import json
import ipaddress
import socket
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping
from urllib.parse import parse_qs, quote, urlparse

import pandas as pd
import requests

from config import settings
from data_loader import (
    DatasetInfo,
    _build_dataset_info,
    _finalise_df,
    _validate_parsed_df,
)
from user_services import is_supabase_service_role_key


class DatabaseConnectionError(ValueError):
    """A safe, user-facing database connection or import error."""


@dataclass(frozen=True)
class TableRef:
    name: str
    schema: str | None = None

    @property
    def label(self) -> str:
        return f"{self.schema}.{self.name}" if self.schema else self.name


def _sql_engine(config: Mapping[str, Any]):
    try:
        from sqlalchemy import URL, create_engine
    except ImportError as exc:
        raise DatabaseConnectionError(
            "SQL database support is not installed. Install the project requirements."
        ) from exc

    provider = config.get("provider")
    username = str(config.get("username", ""))
    password = str(config.get("password", ""))
    host = str(config.get("host", ""))
    database = str(config.get("database", ""))
    try:
        port = int(config.get("port", 0))
    except (TypeError, ValueError) as exc:
        raise DatabaseConnectionError("The database port must be a number.") from exc

    if not all((username, password, host, database)) or not 1 <= port <= 65535:
        raise DatabaseConnectionError(
            "Provide a host, database, username, password, and valid port."
        )
    _validate_public_host(host, port)

    if provider == "PostgreSQL":
        driver = "postgresql+psycopg"
        if config.get("ssl", True):
            import certifi

            query = {
                "sslmode": "verify-full",
                "sslrootcert": certifi.where(),
            }
        else:
            query = {}
        connect_args = {"connect_timeout": 5}
    elif provider == "MySQL":
        driver = "mysql+pymysql"
        query = {}
        connect_args = {
            "connect_timeout": 5,
            "read_timeout": 30,
            "write_timeout": 30,
        }
        if config.get("ssl", True):
            import certifi

            connect_args["ssl"] = {
                "ca": certifi.where(),
                "check_hostname": True,
            }
    else:
        raise DatabaseConnectionError("Choose PostgreSQL or MySQL.")

    try:
        url = URL.create(
            driver,
            username=username,
            password=password,
            host=host,
            port=port,
            database=database,
            query=query,
        )
        return create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    except Exception:
        raise DatabaseConnectionError(
            "Could not initialize the SQL connection. Check the connection details."
        ) from None


def _sql_tables(config: Mapping[str, Any]) -> list[TableRef]:
    from sqlalchemy import inspect

    engine = _sql_engine(config)
    try:
        inspector = inspect(engine)
        if config.get("provider") == "MySQL":
            names = inspector.get_table_names()
            tables = [TableRef(name=name) for name in names]
        else:
            excluded = {"information_schema", "pg_catalog", "pg_toast"}
            schemas = [
                schema for schema in inspector.get_schema_names()
                if schema not in excluded and not schema.startswith("pg_temp_")
            ]
            tables = [
                TableRef(name=name, schema=schema)
                for schema in schemas
                for name in inspector.get_table_names(schema=schema)
            ]
        if not tables:
            raise DatabaseConnectionError("No accessible tables were found.")
        return tables[:500]
    except DatabaseConnectionError:
        raise
    except Exception:
        raise DatabaseConnectionError(
            "Could not list database tables. Check the credentials and read permissions."
        ) from None
    finally:
        engine.dispose()


def _read_sql_table(
    config: Mapping[str, Any], table: TableRef
) -> tuple[pd.DataFrame, str]:
    from sqlalchemy import inspect, text

    engine = _sql_engine(config)
    provider = str(config["provider"])
    try:
        inspector = inspect(engine)
        columns = inspector.get_columns(table.name, schema=table.schema)
        if len(columns) > settings.max_columns:
            raise DatabaseConnectionError(
                f"This table has {len(columns)} columns; the limit is "
                f"{settings.max_columns}."
            )

        preparer = engine.dialect.identifier_preparer
        table_identifier = preparer.quote(table.name)
        if table.schema:
            table_identifier = (
                f"{preparer.quote_schema(table.schema)}.{table_identifier}"
            )
        query = text(f"SELECT * FROM {table_identifier} LIMIT :row_limit")

        with engine.connect() as connection:
            if provider == "PostgreSQL":
                connection.exec_driver_sql(
                    "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"
                )
            else:
                connection.exec_driver_sql("SET SESSION TRANSACTION READ ONLY")
            connection.commit()
            with connection.begin():
                result = connection.execute(
                    query, {"row_limit": settings.max_rows + 1}
                )
                frame = pd.DataFrame.from_records(
                    result.fetchall(), columns=result.keys()
                )

        if len(frame) > settings.max_rows:
            raise DatabaseConnectionError(
                f"This table exceeds the {settings.max_rows:,}-row import limit. "
                "Choose a smaller table or create a database view with fewer rows."
            )
        return frame, provider
    except DatabaseConnectionError:
        raise
    except Exception:
        raise DatabaseConnectionError(
            "Could not import this table. Check that it exists and your account "
            "has read-only access."
        ) from None
    finally:
        engine.dispose()


def _mongo_collection(config: Mapping[str, Any]):
    try:
        from pymongo import MongoClient
    except ImportError as exc:
        raise DatabaseConnectionError(
            "MongoDB support is not installed. Install the project requirements."
        ) from exc

    uri = str(config.get("uri", "")).strip()
    database = str(config.get("database", "")).strip()
    if not uri.startswith(("mongodb://", "mongodb+srv://")) or not database:
        raise DatabaseConnectionError(
            "Provide a valid MongoDB URI and database name."
        )
    options = {
        name.lower(): values
        for name, values in parse_qs(urlparse(uri).query).items()
    }
    if any(
        values and values[0].lower() in {"true", "1", "yes", "cert_none"}
        for name, values in options.items()
        if name in {
            "tlsinsecure",
            "tlsallowinvalidcertificates",
            "tlsallowinvalidhostnames",
            "ssl_cert_reqs",
        }
    ):
        raise DatabaseConnectionError(
            "MongoDB connections with disabled TLS certificate verification are not allowed."
        )

    if settings.app_env == "production":
        try:
            from pymongo.uri_parser import parse_uri

            parsed_uri = parse_uri(uri, warn=False)
            for host, port in parsed_uri["nodelist"]:
                _validate_public_host(host, port)
        except DatabaseConnectionError:
            raise
        except Exception:
            raise DatabaseConnectionError(
                "The MongoDB URI is invalid or resolves to a blocked network address."
            ) from None

    client = None
    try:
        client = MongoClient(
            uri,
            tls=bool(config.get("ssl", True)),
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            socketTimeoutMS=30000,
        )
        client.admin.command("ping")
        return client
    except Exception:
        if client is not None:
            client.close()
        raise DatabaseConnectionError(
            "Could not connect to MongoDB. Check the URI, network access, and credentials."
        ) from None


def _mongo_tables(config: Mapping[str, Any]) -> list[TableRef]:
    client = _mongo_collection(config)
    try:
        names = client[str(config["database"])].list_collection_names()
        if not names:
            raise DatabaseConnectionError("No accessible collections were found.")
        return [TableRef(name=name) for name in names[:500]]
    except DatabaseConnectionError:
        raise
    except Exception:
        raise DatabaseConnectionError(
            "Could not list MongoDB collections. Check the database permissions."
        ) from None
    finally:
        client.close()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=True, default=str)
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=True, default=str)
    if isinstance(value, Decimal):
        return float(value)
    if value.__class__.__module__.startswith("bson"):
        return str(value)
    return value


def _read_mongo_collection(
    config: Mapping[str, Any], table: TableRef
) -> tuple[pd.DataFrame, str]:
    client = _mongo_collection(config)
    try:
        collection = client[str(config["database"])][table.name]
        documents = list(
            collection.find({}, max_time_ms=10_000).limit(settings.max_rows + 1)
        )
        if len(documents) > settings.max_rows:
            raise DatabaseConnectionError(
                f"This collection exceeds the {settings.max_rows:,}-document import "
                "limit. Choose a smaller collection."
            )
        rows = [
            {key: _json_safe(value) for key, value in document.items()}
            for document in documents
        ]
        frame = pd.DataFrame(rows)
        if len(frame.columns) > settings.max_columns:
            raise DatabaseConnectionError(
                f"This collection has more than {settings.max_columns} fields, "
                "which exceeds the import limit."
            )
        return frame, "MongoDB"
    except DatabaseConnectionError:
        raise
    except Exception:
        raise DatabaseConnectionError(
            "Could not import this collection. Check that it exists and your account "
            "has read permissions."
        ) from None
    finally:
        client.close()


def _supabase_base_url(config: Mapping[str, Any]) -> str:
    url = str(config.get("url", "")).strip().rstrip("/")
    key = str(config.get("key", "")).strip()
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.endswith(".supabase.co")
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or not key
    ):
        raise DatabaseConnectionError(
            "Provide an HTTPS Supabase project URL and its anon/publishable key. "
            "Do not use a service-role key."
        )
    if is_supabase_service_role_key(key):
        raise DatabaseConnectionError(
            "Service-role keys are blocked. Use an anon/publishable key and, if needed, "
            "a user access token."
        )
    return url


def _validate_public_host(host: str, port: int) -> None:
    if settings.app_env != "production":
        return
    host = host.strip().strip("[]").rstrip(".")
    if not host or host.lower() == "localhost" or host.lower().endswith(".localhost"):
        raise DatabaseConnectionError(
            "Production database connections must use a public database host."
        )
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        }
    except OSError:
        raise DatabaseConnectionError(
            "The database host could not be resolved."
        ) from None
    if not addresses or any(
        not ipaddress.ip_address(address).is_global for address in addresses
    ):
        raise DatabaseConnectionError(
            "Production database connections cannot target private, local, or reserved networks."
        )


def _supabase_headers(key: str, access_token: str = "") -> dict[str, str]:
    headers = {"apikey": key}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


def _supabase_tables(config: Mapping[str, Any]) -> list[TableRef]:
    base_url = _supabase_base_url(config)
    key = str(config["key"]).strip()
    try:
        response = requests.get(
            f"{base_url}/rest/v1/",
            headers={
                **_supabase_headers(
                    key, str(config.get("access_token", "")).strip()
                ),
                "Accept": "application/openapi+json",
            },
            timeout=10,
        )
        if response.status_code >= 400:
            raise DatabaseConnectionError(
                "Supabase could not list accessible tables. Check the project URL, "
                "key, and Data API access."
            )
        paths = response.json().get("paths", {})
        names = sorted({
            path.strip("/").split("/", 1)[0]
            for path, operations in paths.items()
            if path.count("/") == 1
            and path.startswith("/")
            and path.strip("/")
            and not path.startswith("/rpc/")
            and "get" in operations
        })
    except DatabaseConnectionError:
        raise
    except Exception:
        raise DatabaseConnectionError(
            "Could not reach the Supabase Data API. Check the project URL and key."
        ) from None
    if not names:
        raise DatabaseConnectionError(
            "No accessible Supabase tables were found. Check Data API exposure and "
            "row-level security policies."
        )
    return [TableRef(name=name) for name in names[:500]]


def _read_supabase_table(
    config: Mapping[str, Any], table: TableRef
) -> tuple[pd.DataFrame, str]:
    base_url = _supabase_base_url(config)
    key = str(config["key"]).strip()
    path = quote(table.name, safe="")
    try:
        response = requests.get(
            f"{base_url}/rest/v1/{path}",
            params={"select": "*", "limit": settings.max_rows + 1},
            headers=_supabase_headers(
                key, str(config.get("access_token", "")).strip()
            ),
            timeout=30,
        )
        if response.status_code >= 400:
            raise DatabaseConnectionError(
                "Supabase could not read this table. Check the table name, Data API "
                "access, and row-level security policy."
            )
        rows = response.json()
        if not isinstance(rows, list):
            raise DatabaseConnectionError("Supabase returned an unexpected table response.")
        if rows and len(rows[0]) > settings.max_columns:
            raise DatabaseConnectionError(
                f"This table has more than {settings.max_columns} columns, "
                "which exceeds the import limit."
            )
        if len(rows) > settings.max_rows:
            raise DatabaseConnectionError(
                f"This table exceeds the {settings.max_rows:,}-row import limit. "
                "Choose a smaller table or create a database view with fewer rows."
            )
        frame = pd.DataFrame.from_records(rows)
        if len(frame.columns) > settings.max_columns:
            raise DatabaseConnectionError(
                f"This table has more than {settings.max_columns} columns, "
                "which exceeds the import limit."
            )
        return frame, "Supabase"
    except DatabaseConnectionError:
        raise
    except Exception:
        raise DatabaseConnectionError(
            "Could not import this Supabase table. Check its Data API and read policies."
        ) from None


def list_tables(config: Mapping[str, Any]) -> list[TableRef]:
    provider = config.get("provider")
    if provider in {"PostgreSQL", "MySQL"}:
        return _sql_tables(config)
    if provider == "MongoDB":
        return _mongo_tables(config)
    if provider == "Supabase":
        return _supabase_tables(config)
    raise DatabaseConnectionError("Choose a supported database provider.")


def import_table(
    config: Mapping[str, Any], table: TableRef
) -> DatasetInfo:
    provider = config.get("provider")
    if provider in {"PostgreSQL", "MySQL"}:
        frame, file_format = _read_sql_table(config, table)
    elif provider == "MongoDB":
        frame, file_format = _read_mongo_collection(config, table)
    elif provider == "Supabase":
        frame, file_format = _read_supabase_table(config, table)
    else:
        raise DatabaseConnectionError("Choose a supported database provider.")

    if frame.empty:
        raise DatabaseConnectionError("The selected table or collection has no data.")
    frame = _finalise_df(frame)
    filename = table.label
    warnings = _validate_parsed_df(frame, filename)
    return _build_dataset_info(
        frame,
        filename,
        file_format,
        int(frame.memory_usage(deep=True).sum()),
        "database",
        warnings,
    )
