"""Async PostgreSQL SQL executor using asyncpg."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from pg_diag.artifact import item_from_plan
from pg_diag.content_loader import ContentPack
from pg_diag.errors import PgDiagError
from pg_diag.executors.common import elapsed_ms, exception_diagnostic
from pg_diag.planner import PlannedItem
from pg_diag.security import json_safe, redact_error, redact_row


class MissingAsyncpgError(PgDiagError):
    pass


INTERNAL_TAG_PREFIX = "tag_"
INTERNAL_TIME_COLUMN = "epoch_ns"
SEVERITY_LEVEL_RANK = {"ok": 0, "unknown": 1, "medium": 2, "high": 3}


def _load_asyncpg():
    try:
        import asyncpg  # type: ignore
    except ModuleNotFoundError as exc:
        raise MissingAsyncpgError(
            "asyncpg is not installed. Install pg_diag runtime dependencies before running snapshot."
        ) from exc
    return asyncpg


async def connect(dsn: str | None = None, **kwargs: Any):
    asyncpg = _load_asyncpg()
    if dsn:
        return await asyncpg.connect(dsn=dsn)
    return await asyncpg.connect(**{key: value for key, value in kwargs.items() if value is not None})


async def detect_runtime_context(conn: Any) -> dict[str, Any]:
    server_version_num = int(await conn.fetchval("select current_setting('server_version_num')::int"))
    server_version = await conn.fetchval("select version()")
    current_database = await conn.fetchval("select current_database()")
    current_user = await conn.fetchval("select current_user")
    in_recovery = await conn.fetchval("select pg_is_in_recovery()")
    return {
        "server_version_num": server_version_num,
        "server_version": json_safe(server_version),
        "current_database": json_safe(current_database),
        "current_user": json_safe(current_user),
        "in_recovery": bool(in_recovery),
        "capabilities": {},
    }


async def execute_query_item(content: ContentPack, conn: Any, planned: PlannedItem) -> dict[str, Any]:
    started = time.perf_counter()
    sql_file = planned.sql_file
    if not sql_file:
        return item_from_plan(
            planned,
            collection_status="unsupported",
            reason=planned.reason or "No SQL variant selected",
            result={"kind": "table", "columns": [], "rows": [], "row_count": 0},
        )

    sql_root = (content.query_catalog.get("query_catalog") or {}).get("sql_root", "queries")
    sql_path = content.path / sql_root / sql_file
    sql_text = Path(sql_path).read_text(encoding="utf-8")

    try:
        async with conn.transaction(readonly=True):
            await _set_local_runtime_guards(content, conn)
            prepared = await conn.prepare(sql_text)
            raw_columns = _columns_from_prepared(prepared)
            records = await prepared.fetch()
            raw_rows = [
                redact_row(raw_columns, [record[column["name"]] for column in raw_columns])
                for record in records
            ]
            columns, rows = publicize_table_result(raw_columns, raw_rows)
    except Exception as exc:
        status = _classify_sql_error(exc, planned)
        message = redact_error(exc)
        return item_from_plan(
            planned,
            collection_status=status,
            reason=message,
            timing_ms=elapsed_ms(started),
            result={"kind": "table", "columns": [], "rows": [], "row_count": 0},
            diagnostics=[_sql_exception_diagnostic(status, message, exc)],
            source_text=sql_text,
            source_language="sql",
        )

    status = "ok" if rows else "empty"
    severity_level = infer_table_severity_level(columns, rows)
    return item_from_plan(
        planned,
        collection_status=status,
        severity_level=severity_level,
        timing_ms=elapsed_ms(started),
        result={"kind": "table", "columns": columns, "rows": rows, "row_count": len(rows)},
        source_text=sql_text,
        source_language="sql",
    )


async def _set_local_runtime_guards(content: ContentPack, conn: Any) -> None:
    policy = content.report.get("runtime_policy") or {}
    statement_timeout = str(policy.get("default_sql_timeout_ms", 10000))
    await conn.execute("select set_config('statement_timeout', $1, true)", statement_timeout)
    await conn.execute("select set_config('lock_timeout', $1, true)", "1000")
    await conn.execute("select set_config('idle_in_transaction_session_timeout', $1, true)", "10000")
    await conn.execute("select set_config('search_path', $1, true)", "pg_catalog, public")


def _columns_from_prepared(prepared: Any) -> list[dict[str, Any]]:
    columns = []
    for attr in prepared.get_attributes():
        attr_type = getattr(attr, "type", None)
        columns.append(
            {
                "name": attr.name,
                "pg_type": getattr(attr_type, "name", None),
                "pg_type_oid": getattr(attr_type, "oid", None),
            }
        )
    return columns


def publicize_table_result(
    raw_columns: list[dict[str, Any]],
    raw_rows: list[list[Any]],
) -> tuple[list[dict[str, Any]], list[list[Any]]]:
    visible_indexes: list[int] = []
    public_columns: list[dict[str, Any]] = []
    used_names: set[str] = set()

    for index, column in enumerate(raw_columns):
        raw_name = str(column.get("name") or "")
        if raw_name == INTERNAL_TIME_COLUMN:
            continue
        public_name = public_column_name(raw_name)
        public_name = _dedupe_column_name(public_name, used_names)
        used_names.add(public_name)

        public_column = dict(column)
        public_column["name"] = public_name
        public_columns.append(public_column)
        visible_indexes.append(index)

    public_rows = [
        [row[index] if index < len(row) else None for index in visible_indexes]
        for row in raw_rows
    ]
    return public_columns, public_rows


def public_column_name(name: str) -> str:
    if name.startswith(INTERNAL_TAG_PREFIX):
        return name[len(INTERNAL_TAG_PREFIX) :]
    return name


def _dedupe_column_name(name: str, used_names: set[str]) -> str:
    if name not in used_names:
        return name
    counter = 2
    while f"{name}_{counter}" in used_names:
        counter += 1
    return f"{name}_{counter}"


def infer_table_severity_level(
    columns: list[dict[str, Any]],
    rows: list[list[Any]],
) -> str | None:
    column_names = [str(column.get("name") or "").strip().lower() for column in columns]
    severity_indexes = [
        index
        for index, name in enumerate(column_names)
        if name in {"risk_level", "severity_level"}
    ]
    if not severity_indexes:
        return None
    if not rows:
        return "ok"

    best = "ok"
    for row in rows:
        for index in severity_indexes:
            if index >= len(row):
                continue
            level = str(row[index] or "").strip().lower()
            if level not in SEVERITY_LEVEL_RANK:
                continue
            if SEVERITY_LEVEL_RANK[level] > SEVERITY_LEVEL_RANK[best]:
                best = level
    return best


def _classify_sql_error(exc: Exception, planned: PlannedItem) -> str:
    name = exc.__class__.__name__
    if "FeatureNotSupported" in name:
        return "unsupported"
    if _is_missing_optional_relation(exc, planned):
        return "unsupported"
    return "error"


def _is_missing_optional_relation(exc: Exception, planned: PlannedItem) -> bool:
    name = exc.__class__.__name__
    sqlstate = getattr(exc, "sqlstate", None)
    return bool(planned.source_metadata.get("optional")) and (
        "UndefinedTable" in name or sqlstate == "42P01"
    )


def _sql_exception_diagnostic(status: str, message: str, exc: BaseException) -> dict[str, Any]:
    level = "error" if status == "error" else "warning"
    return exception_diagnostic(status, message, exc, level=level)
