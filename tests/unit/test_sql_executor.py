from __future__ import annotations

import asyncio
from types import SimpleNamespace

from pg_diag.executors.sql import execute_query_item
from pg_diag.planner import PlannedItem


class QueryCanceledError(Exception):
    pass


class UndefinedTableError(Exception):
    sqlstate = "42P01"


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
