from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from pg_diag.errors import PgDiagError
from pg_diag.executors.sql import connect, execute_query_item
from pg_diag.planner import PlannedItem


class QueryCanceledError(Exception):
    pass


class UndefinedTableError(Exception):
    sqlstate = "42P01"


class UndefinedColumnError(Exception):
    sqlstate = "42703"


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class TimeoutPrepared:
    def get_attributes(self):
        return []

    async def fetch(self):
        raise QueryCanceledError("canceling statement due to statement timeout")


class MissingRelationPrepared:
    def get_attributes(self):
        return []

    async def fetch(self):
        raise UndefinedTableError('relation "pg_wait_sampling_profile" does not exist')


class MissingColumnPrepared:
    def get_attributes(self):
        return []

    async def fetch(self):
        raise UndefinedColumnError('column "stats_since" does not exist')


class FakeAttribute:
    def __init__(self, name: str) -> None:
        self.name = name
        self.type = SimpleNamespace(name="text", oid=25)


class RowsPrepared:
    def __init__(self, columns: list[str], rows: list[dict[str, object]]) -> None:
        self.columns = columns
        self.rows = rows

    def get_attributes(self):
        return [FakeAttribute(column) for column in self.columns]

    async def fetch(self):
        return self.rows


class TimeoutConn:
    def __init__(self, prepared=None) -> None:
        self.executed: list[tuple[str, str]] = []
        self.prepared = prepared or TimeoutPrepared()

    def transaction(self, readonly: bool):
        assert readonly is True
        return FakeTransaction()

    async def execute(self, sql: str, value: str) -> None:
        self.executed.append((sql, value))

    async def prepare(self, sql: str):
        return self.prepared


class ConnectTestConn:
    def __init__(self, session_default: str = "on", current_transaction: str = "on") -> None:
        self.session_default = session_default
        self.current_transaction = current_transaction
        self.closed = False
        self.verification_sql: str | None = None

    async def fetchrow(self, sql: str):
        self.verification_sql = sql
        return {
            "session_default": self.session_default,
            "current_transaction": self.current_transaction,
        }

    async def close(self) -> None:
        self.closed = True


class AsyncpgConnectStub:
    def __init__(self, conn: ConnectTestConn) -> None:
        self.conn = conn
        self.calls: list[dict[str, object]] = []

    async def connect(self, **kwargs):
        self.calls.append(kwargs)
        return self.conn


def test_connect_dsn_enforces_read_only_startup_setting(monkeypatch) -> None:
    conn = ConnectTestConn()
    asyncpg = AsyncpgConnectStub(conn)
    monkeypatch.setattr("pg_diag.executors.sql._load_asyncpg", lambda: asyncpg)

    result = asyncio.run(
        connect(
            dsn="postgresql://app@example/appdb",
            host="ignored-with-dsn",
            server_settings={
                "application_name": "pg_diag",
                "default_transaction_read_only": "off",
            },
        )
    )

    assert result is conn
    assert asyncpg.calls == [
        {
            "dsn": "postgresql://app@example/appdb",
            "server_settings": {
                "application_name": "pg_diag",
                "default_transaction_read_only": "on",
            },
        }
    ]
    assert "transaction_read_only" in str(conn.verification_sql)


def test_connect_parameters_enforce_read_only_startup_setting(monkeypatch) -> None:
    conn = ConnectTestConn()
    asyncpg = AsyncpgConnectStub(conn)
    monkeypatch.setattr("pg_diag.executors.sql._load_asyncpg", lambda: asyncpg)

    asyncio.run(
        connect(
            host="db.example",
            port=5432,
            database="appdb",
            user="app",
            password=None,
        )
    )

    assert asyncpg.calls == [
        {
            "host": "db.example",
            "port": 5432,
            "database": "appdb",
            "user": "app",
            "server_settings": {"default_transaction_read_only": "on"},
        }
    ]


def test_connect_fails_closed_when_session_is_not_read_only(monkeypatch) -> None:
    conn = ConnectTestConn(session_default="off", current_transaction="off")
    asyncpg = AsyncpgConnectStub(conn)
    monkeypatch.setattr("pg_diag.executors.sql._load_asyncpg", lambda: asyncpg)

    with pytest.raises(PgDiagError, match="connection is not read-only"):
        asyncio.run(connect(host="db.example", database="appdb", user="app"))

    assert conn.closed is True


def test_sql_timeout_exception_is_recorded_in_item(tmp_path) -> None:
    queries = tmp_path / "queries"
    queries.mkdir()
    (queries / "slow.sql").write_text("select pg_sleep(10)", encoding="utf-8")
    content = SimpleNamespace(
        path=tmp_path,
        query_catalog={"query_catalog": {"sql_root": "queries"}},
        report={"runtime_policy": {"default_sql_timeout_ms": 3000}},
    )
    planned = PlannedItem(
        item_id="test.slow",
        section_id="test",
        item_key="slow",
        title="Slow SQL",
        source_kind="query",
        status="planned",
        source_id="test.slow",
        sql_file="slow.sql",
        source_metadata={"query_id": "test.slow"},
    )
    conn = TimeoutConn()

    item = asyncio.run(execute_query_item(content, conn, planned))

    assert ("select set_config('statement_timeout', $1, true)", "3000") in conn.executed
    assert item["item_id"] == "test.slow"
    assert item["collection_status"] == "error"
    assert item["severity_level"] == "unknown"
    assert "statement timeout" in item["reason"]
    assert item["result"] == {"kind": "table", "columns": [], "rows": [], "row_count": 0}
    assert item["source_metadata"]["source_text"] == "select pg_sleep(10)"
    assert item["source_metadata"]["source_language"] == "sql"
    assert item["diagnostics"][0]["code"] == "error"
    assert "statement timeout" in item["diagnostics"][0]["message"]
    assert "QueryCanceledError" in item["diagnostics"][0]["traceback"]


def test_optional_missing_relation_is_recorded_as_unsupported(tmp_path) -> None:
    queries = tmp_path / "queries"
    queries.mkdir()
    (queries / "pg_wait_sampling_profile.sql").write_text(
        "select * from pg_wait_sampling_profile",
        encoding="utf-8",
    )
    content = SimpleNamespace(
        path=tmp_path,
        query_catalog={"query_catalog": {"sql_root": "queries"}},
        report={"runtime_policy": {"default_sql_timeout_ms": 3000}},
    )
    planned = PlannedItem(
        item_id="activity_locks.pg_wait_sampling_profile",
        section_id="activity_locks",
        item_key="pg_wait_sampling_profile",
        title="pg_wait_sampling Profile",
        source_kind="query",
        status="planned",
        source_id="wait.pg_wait_sampling_profile",
        sql_file="pg_wait_sampling_profile.sql",
        source_metadata={"query_id": "wait.pg_wait_sampling_profile", "optional": True},
    )
    conn = TimeoutConn(MissingRelationPrepared())

    item = asyncio.run(execute_query_item(content, conn, planned))

    assert item["collection_status"] == "unsupported"
    assert item["result"] == {"kind": "table", "columns": [], "rows": [], "row_count": 0}
    assert item["diagnostics"][0]["level"] == "warning"
    assert item["diagnostics"][0]["code"] == "unsupported"


def test_optional_extension_shape_mismatch_is_recorded_as_unsupported(tmp_path) -> None:
    queries = tmp_path / "queries"
    queries.mkdir()
    (queries / "top_sql.sql").write_text(
        "select stats_since from pg_stat_statements",
        encoding="utf-8",
    )
    content = SimpleNamespace(
        path=tmp_path,
        query_catalog={"query_catalog": {"sql_root": "queries"}},
        report={"runtime_policy": {"default_sql_timeout_ms": 3000}},
    )
    planned = PlannedItem(
        item_id="sql_workload.top_sql_by_total_time",
        section_id="sql_workload",
        item_key="top_sql_by_total_time",
        title="Top SQL By Total Time",
        source_kind="query",
        status="planned",
        source_id="statements.top_by_total_time",
        sql_file="top_sql.sql",
        source_metadata={"query_id": "statements.top_by_total_time", "optional": True},
    )
    conn = TimeoutConn(MissingColumnPrepared())

    item = asyncio.run(execute_query_item(content, conn, planned))

    assert item["collection_status"] == "unsupported"
    assert item["diagnostics"][0]["level"] == "warning"
    assert item["diagnostics"][0]["code"] == "unsupported"


def test_sql_result_risk_level_sets_item_severity(tmp_path) -> None:
    queries = tmp_path / "queries"
    queries.mkdir()
    (queries / "security.sql").write_text("select 'medium' as risk_level", encoding="utf-8")
    content = SimpleNamespace(
        path=tmp_path,
        query_catalog={"query_catalog": {"sql_root": "queries"}},
        report={"runtime_policy": {"default_sql_timeout_ms": 3000}},
    )
    planned = PlannedItem(
        item_id="overview.security_logging_settings",
        section_id="overview",
        item_key="security_logging_settings",
        title="Security Logging Settings",
        source_kind="query",
        status="planned",
        source_id="security.security_logging_settings",
        sql_file="security.sql",
        source_metadata={"query_id": "security.security_logging_settings"},
    )
    conn = TimeoutConn(
        RowsPrepared(
            ["setting_name", "risk_level", "risk_reason"],
            [
                {
                    "setting_name": "log_connections",
                    "risk_level": "medium",
                    "risk_reason": "connection attempts are not logged",
                },
                {
                    "setting_name": "log_statement",
                    "risk_level": "high",
                    "risk_reason": "DDL statements are not logged",
                },
            ],
        )
    )

    item = asyncio.run(execute_query_item(content, conn, planned))

    assert item["collection_status"] == "ok"
    assert item["severity_level"] == "high"
    assert item["issues"]["summary"]["severity"] == "high"
    assert item["issues"]["summary"]["status"] == "fail"
    assert "connection attempts are not logged" in item["issues"]["summary"]["description"]


def test_sql_internal_evaluation_columns_create_summary_but_stay_hidden(tmp_path) -> None:
    queries = tmp_path / "queries"
    queries.mkdir()
    (queries / "settings.sql").write_text("select * from pg_settings", encoding="utf-8")
    content = SimpleNamespace(
        path=tmp_path,
        query_catalog={"query_catalog": {"sql_root": "queries"}},
        report={"runtime_policy": {"default_sql_timeout_ms": 3000}},
    )
    planned = PlannedItem(
        item_id="overview.pg_settings",
        section_id="overview",
        item_key="pg_settings",
        title="PostgreSQL Settings",
        source_kind="query",
        status="planned",
        source_id="cluster.settings",
        sql_file="settings.sql",
        source_metadata={
            "query_id": "cluster.settings",
            "evaluation": {
                "summary_title": "PostgreSQL settings require review",
                "recommendation": "Validate work_mem before changing it globally.",
            },
        },
    )
    conn = TimeoutConn(
        RowsPrepared(
            ["setting_name", "setting_value", "pg_diag_internal_severity", "pg_diag_internal_reason"],
            [
                {
                    "setting_name": "work_mem",
                    "setting_value": "4096",
                    "pg_diag_internal_severity": "medium",
                    "pg_diag_internal_reason": "work_mem remains at the PostgreSQL default",
                }
            ],
        )
    )

    item = asyncio.run(execute_query_item(content, conn, planned))

    assert item["severity_level"] == "medium"
    assert [column["name"] for column in item["result"]["columns"]] == [
        "setting_name",
        "setting_value",
    ]
    assert item["result"]["rows"] == [["work_mem", "4096"]]
    assert item["issues"]["summary"] == {
        "severity": "medium",
        "status": "review",
        "title": "PostgreSQL settings require review",
        "description": (
            "1 finding row(s); highest severity is medium. "
            "work_mem remains at the PostgreSQL default"
        ),
        "recommendation": "Validate work_mem before changing it globally.",
    }


def test_empty_sql_result_with_risk_level_column_is_ok_severity(tmp_path) -> None:
    queries = tmp_path / "queries"
    queries.mkdir()
    (queries / "security.sql").write_text("select 'medium' as risk_level where false", encoding="utf-8")
    content = SimpleNamespace(
        path=tmp_path,
        query_catalog={"query_catalog": {"sql_root": "queries"}},
        report={"runtime_policy": {"default_sql_timeout_ms": 3000}},
    )
    planned = PlannedItem(
        item_id="overview.security_logging_settings",
        section_id="overview",
        item_key="security_logging_settings",
        title="Security Logging Settings",
        source_kind="query",
        status="planned",
        source_id="security.security_logging_settings",
        sql_file="security.sql",
        source_metadata={"query_id": "security.security_logging_settings"},
    )
    conn = TimeoutConn(RowsPrepared(["setting_name", "risk_level"], []))

    item = asyncio.run(execute_query_item(content, conn, planned))

    assert item["collection_status"] == "empty"
    assert item["severity_level"] == "ok"
