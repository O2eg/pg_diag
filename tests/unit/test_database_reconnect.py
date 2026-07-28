from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from pg_diag import runtime_config
import pg_diag.collection as collection_module
import pg_diag.snapshots as snapshots_module
from pg_diag.errors import DatabaseIdentityChangedError, DatabaseUnavailableError


IDENTITY = {
    "current_database": "app",
    "server_version_num": 180000,
    "in_recovery": False,
    "database_host_ip": "192.0.2.10",
}


class FakeConnection:
    def __init__(self, *, closed: bool = False) -> None:
        self.closed = closed
        self.close_calls = 0
        self.terminate_calls = 0

    def is_closed(self) -> bool:
        return self.closed

    async def close(self) -> None:
        self.close_calls += 1
        self.closed = True

    def terminate(self) -> None:
        self.terminate_calls += 1
        self.closed = True


class SuccessfulConnector:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.open_calls = 0
        self.timeout_seconds: list[float | None] = []

    async def open(self, *, timeout_seconds: float | None = None) -> FakeConnection:
        self.open_calls += 1
        self.timeout_seconds.append(timeout_seconds)
        return self.connection


class FailingConnector:
    def __init__(self) -> None:
        self.open_calls = 0
        self.timeout_seconds: list[float | None] = []

    async def open(self, *, timeout_seconds: float | None = None) -> FakeConnection:
        self.open_calls += 1
        self.timeout_seconds.append(timeout_seconds)
        raise ConnectionRefusedError("network is unreachable")


def test_closed_connection_is_reopened_and_operation_is_repeated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = FakeConnection()
    replacement = FakeConnection()
    connector = SuccessfulConnector(replacement)
    run = SimpleNamespace(
        conn=original,
        database_connector=connector,
        database_identity=dict(IDENTITY),
        progress=None,
    )
    calls = 0

    async def detect_stub(conn):
        assert conn is replacement
        return dict(IDENTITY)

    async def operation(conn):
        nonlocal calls
        calls += 1
        if conn is original:
            conn.closed = True
            raise RuntimeError(
                "cannot call Transaction.__aexit__(): the underlying connection is closed"
            )
        return "collected"

    monkeypatch.setattr(runtime_config, "DATABASE_RECONNECT_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(collection_module, "detect_runtime_context", detect_stub)

    result = asyncio.run(
        collection_module.execute_with_database_reconnect(
            run,
            operation,
            operation="sample:11/21",
        )
    )

    assert result == "collected"
    assert calls == 2
    assert connector.open_calls == 1
    assert connector.timeout_seconds == [
        runtime_config.DATABASE_RECONNECT_CONNECT_TIMEOUT_SECONDS
    ]
    assert original.close_calls == 1
    assert run.conn is replacement


def test_unavailable_host_stops_after_five_reconnect_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = FakeConnection(closed=True)
    connector = FailingConnector()
    run = SimpleNamespace(
        conn=original,
        database_connector=connector,
        database_identity=dict(IDENTITY),
        progress=None,
    )

    async def operation(_conn):
        raise RuntimeError("the underlying connection is closed")

    monkeypatch.setattr(runtime_config, "DATABASE_RECONNECT_DELAY_SECONDS", 0.0)

    with pytest.raises(
        DatabaseUnavailableError,
        match=r"database host is unavailable.*after 5 attempts",
    ):
        asyncio.run(
            collection_module.execute_with_database_reconnect(
                run,
                operation,
                operation="sample:11/21",
            )
        )

    assert connector.open_calls == 5
    assert connector.timeout_seconds == [
        runtime_config.DATABASE_RECONNECT_CONNECT_TIMEOUT_SECONDS
    ] * 5
    assert original.close_calls == 1


def test_reconnect_rejects_changed_database_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = FakeConnection(closed=True)
    replacement = FakeConnection()
    connector = SuccessfulConnector(replacement)
    run = SimpleNamespace(
        conn=original,
        database_connector=connector,
        database_identity=dict(IDENTITY),
        progress=None,
    )

    async def detect_stub(_conn):
        return {**IDENTITY, "database_host_ip": "192.0.2.11"}

    async def operation(_conn):
        raise RuntimeError("the underlying connection is closed")

    monkeypatch.setattr(runtime_config, "DATABASE_RECONNECT_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(collection_module, "detect_runtime_context", detect_stub)

    with pytest.raises(
        DatabaseIdentityChangedError,
        match="refusing to merge samples",
    ):
        asyncio.run(
            collection_module.execute_with_database_reconnect(
                run,
                operation,
                operation="sample:11/21",
            )
        )

    assert connector.open_calls == 1
    assert connector.timeout_seconds == [
        runtime_config.DATABASE_RECONNECT_CONNECT_TIMEOUT_SECONDS
    ]
    assert replacement.close_calls == 1


def test_close_connection_terminates_after_bounded_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class HangingConnection(FakeConnection):
        async def close(self) -> None:
            self.close_calls += 1
            await asyncio.Event().wait()

    conn = HangingConnection()
    monkeypatch.setattr(
        runtime_config,
        "DATABASE_CONNECTION_CLOSE_TIMEOUT_SECONDS",
        0.001,
    )

    asyncio.run(collection_module.close_connection(conn))

    assert conn.close_calls == 1
    assert conn.terminate_calls == 1
    assert conn.closed is True


def test_snapshot_reconnect_repeats_and_discards_partial_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = FakeConnection()
    replacement = FakeConnection()
    connector = SuccessfulConnector(replacement)
    run = SimpleNamespace(
        conn=original,
        database_connector=connector,
        database_identity=dict(IDENTITY),
        progress=None,
    )
    calls: list[FakeConnection] = []

    async def detect_stub(conn):
        assert conn is replacement
        return dict(IDENTITY)

    async def execute_batch_stub(_content, conn, _queries, **_kwargs):
        calls.append(conn)
        if conn is original:
            conn.closed = True
            return (
                {"timestamp": "partial", "items": {"partial": {}}},
                {"partial": {"collection_status": "ok"}},
                {},
            )
        return (
            {"timestamp": "complete", "items": {"complete": {}}},
            {"complete": {"collection_status": "ok"}},
            {},
        )

    monkeypatch.setattr(runtime_config, "DATABASE_RECONNECT_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(runtime_config, "snapshots_schedule_offsets", lambda *_args: [0.0])
    monkeypatch.setattr(collection_module, "detect_runtime_context", detect_stub)
    monkeypatch.setattr(snapshots_module, "_execute_query_batch", execute_batch_stub)

    snapshots, diagnostics, latest_items = asyncio.run(
        snapshots_module._collect_db_samples(
            SimpleNamespace(),
            original,
            [SimpleNamespace()],
            30.0,
            15.0,
            run=run,
        )
    )

    assert calls == [original, replacement]
    assert snapshots == [{"timestamp": "complete", "items": {"complete": {}}}]
    assert diagnostics == []
    assert latest_items == {"complete": {"collection_status": "ok"}}
    assert "partial" not in latest_items
    assert run.conn is replacement
