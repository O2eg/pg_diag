"""Async PostgreSQL SQL executor using asyncpg."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
import math
import time
from pathlib import Path
from typing import Any

from pg_diag.artifact import item_from_plan
from pg_diag.content_loader import ContentPack
from pg_diag.errors import PgDiagError
from pg_diag.executors.common import elapsed_ms, exception_diagnostic
from pg_diag.planner import PlannedEntry
from pg_diag.security import json_safe, redact_error, redact_row


class MissingAsyncpgError(PgDiagError):
    pass


INTERNAL_TAG_PREFIX = "tag_"
INTERNAL_TIME_COLUMN = "epoch_ns"
INTERNAL_EVALUATION_PREFIX = "pg_diag_internal_"
SEVERITY_LEVEL_RANK = {"ok": 0, "unknown": 1, "medium": 2, "high": 3}
READ_ONLY_SERVER_SETTING = "default_transaction_read_only"
READ_ONLY_SERVER_VALUE = "on"


def _load_asyncpg():
    try:
        import asyncpg  # type: ignore
    except ModuleNotFoundError as exc:
        raise MissingAsyncpgError(
            "asyncpg is not installed. Install pg_diag runtime dependencies before running one-shot."
        ) from exc
    return asyncpg


async def connect(dsn: str | None = None, **kwargs: Any):
    asyncpg = _load_asyncpg()
    server_settings = _read_only_server_settings(kwargs.get("server_settings"))
    connect_kwargs = {
        key: value
        for key, value in kwargs.items()
        if value is not None and key != "server_settings"
    }
    if dsn:
        conn = await asyncpg.connect(
            dsn=dsn,
            **connect_kwargs,
            server_settings=server_settings,
        )
    else:
        conn = await asyncpg.connect(
            **connect_kwargs,
            server_settings=server_settings,
        )
    await _verify_read_only_connection(conn)
    return conn


@dataclass(frozen=True)
class DatabaseConnector:
    """Open verified read-only connections using the collector endpoint."""

    dsn: str | None
    connection_kwargs: Mapping[str, Any]

    @asynccontextmanager
    async def connect(
        self,
        database_name: str,
        *,
        timeout_seconds: float | None = None,
    ):
        if not isinstance(database_name, str) or not database_name.strip():
            raise ValueError("database_name must be a non-empty string")
        if timeout_seconds is not None and (
            not math.isfinite(timeout_seconds) or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be a positive finite number")

        connection_kwargs = dict(self.connection_kwargs)
        connection_kwargs["database"] = database_name
        if timeout_seconds is not None:
            connection_kwargs["timeout"] = timeout_seconds
        conn = await connect(dsn=self.dsn, **connection_kwargs)
        try:
            yield conn
        finally:
            await conn.close()


def _read_only_server_settings(settings: Any) -> dict[str, str]:
    if settings is None:
        result: dict[str, str] = {}
    elif isinstance(settings, Mapping):
        result = {str(key): str(value) for key, value in settings.items()}
    else:
        raise TypeError("server_settings must be a mapping")
    result[READ_ONLY_SERVER_SETTING] = READ_ONLY_SERVER_VALUE
    return result


async def _verify_read_only_connection(conn: Any) -> None:
    try:
        row = await conn.fetchrow(
            "select current_setting('default_transaction_read_only') as session_default, "
            "current_setting('transaction_read_only') as current_transaction"
        )
        session_default = str(row["session_default"]).lower()
        current_transaction = str(row["current_transaction"]).lower()
        if session_default != "on" or current_transaction != "on":
            raise PgDiagError(
                "PostgreSQL connection is not read-only "
                f"(default_transaction_read_only={session_default}, "
                f"transaction_read_only={current_transaction})"
            )
    except BaseException:
        try:
            await conn.close()
        except Exception:
            pass
        raise


async def detect_runtime_context(conn: Any) -> dict[str, Any]:
    row = await conn.fetchrow(
        "select pg_catalog.current_setting('server_version_num')::int as server_version_num, "
        "pg_catalog.version() as server_version, "
        "pg_catalog.current_database() as database_name, "
        "current_user::text as database_user, "
        "pg_catalog.pg_is_in_recovery() as in_recovery, "
        "pg_catalog.host(pg_catalog.inet_server_addr()) as database_host_ip"
    )
    server_version_num = int(row["server_version_num"])
    current_database = json_safe(row["database_name"])
    in_recovery = bool(row["in_recovery"])
    return {
        "server_version_num": server_version_num,
        "server_version": json_safe(row["server_version"]),
        "current_database": current_database,
        "current_user": json_safe(row["database_user"]),
        "in_recovery": in_recovery,
        "database_host_ip": json_safe(row["database_host_ip"]),
        "database_name": current_database,
        "database_role": "Secondary" if in_recovery else "Primary",
        "capabilities": {},
    }


async def execute_query_item(
    content: ContentPack,
    conn: Any,
    planned: PlannedEntry,
) -> dict[str, Any]:
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
    sql_text: str | None = None

    try:
        sql_text = Path(sql_path).read_text(encoding="utf-8")
        async with conn.transaction(readonly=True):
            prepared = await conn.prepare(sql_text)
            raw_columns = _columns_from_prepared(prepared)
            records = await prepared.fetch()
            raw_rows = [
                redact_row(
                    raw_columns,
                    [
                        _record_value(record, index, str(column.get("name") or ""))
                        for index, column in enumerate(raw_columns)
                    ],
                )
                for record in records
            ]
            severity_level, issues = evaluate_table_findings(
                raw_columns,
                raw_rows,
                planned,
            )
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
    result = {"kind": "table", "columns": columns, "rows": rows, "row_count": len(rows)}
    column_statuses = planned.source_metadata.get("column_statuses") or {}
    if column_statuses:
        result["column_statuses"] = column_statuses
    return item_from_plan(
        planned,
        collection_status=status,
        severity_level=severity_level,
        issues=issues,
        timing_ms=elapsed_ms(started),
        result=result,
        source_text=sql_text,
        source_language="sql",
    )


def runtime_guard_server_settings(content: ContentPack) -> dict[str, str]:
    """Return session-level guard settings applied at connection startup."""
    policy = content.report.get("runtime_policy") or {}
    return {
        "statement_timeout": str(policy.get("default_sql_timeout_ms", 10000)),
        "lock_timeout": "1000",
        "idle_in_transaction_session_timeout": "10000",
        "search_path": "pg_catalog, public",
    }


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


def _record_value(record: Any, index: int, name: str) -> Any:
    """Prefer positional access so duplicate SQL column names stay distinct."""
    try:
        return record[index]
    except (IndexError, KeyError, TypeError):
        return record[name]


def publicize_table_result(
    raw_columns: list[dict[str, Any]],
    raw_rows: list[list[Any]],
) -> tuple[list[dict[str, Any]], list[list[Any]]]:
    visible_indexes: list[int] = []
    public_columns: list[dict[str, Any]] = []
    used_names: set[str] = set()

    for index, column in enumerate(raw_columns):
        raw_name = str(column.get("name") or "")
        if raw_name == INTERNAL_TIME_COLUMN or raw_name.startswith(INTERNAL_EVALUATION_PREFIX):
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
        if name in {
            "risk_level",
            "severity_level",
            f"{INTERNAL_EVALUATION_PREFIX}severity",
        }
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


def evaluate_table_findings(
    columns: list[dict[str, Any]],
    rows: list[list[Any]],
    planned: PlannedEntry,
) -> tuple[str | None, dict[str, Any]]:
    column_names = [str(column.get("name") or "").strip().lower() for column in columns]
    severity_index = next(
        (
            index
            for index, name in enumerate(column_names)
            if name in {
                "risk_level",
                "severity_level",
                f"{INTERNAL_EVALUATION_PREFIX}severity",
            }
        ),
        None,
    )
    if severity_index is None:
        return None, {}
    if not rows:
        return "ok", {}

    reason_index = next(
        (
            index
            for index, name in enumerate(column_names)
            if name in {
                "risk_reason",
                "severity_reason",
                f"{INTERNAL_EVALUATION_PREFIX}reason",
            }
        ),
        None,
    )
    finding_levels: list[str] = []
    reasons: list[str] = []
    for row in rows:
        if severity_index >= len(row):
            continue
        level = str(row[severity_index] or "").strip().lower()
        if level not in SEVERITY_LEVEL_RANK:
            continue
        if level in {"medium", "high", "unknown"}:
            finding_levels.append(level)
            if reason_index is not None and reason_index < len(row):
                reason = str(row[reason_index] or "").strip()
                if reason and reason not in reasons:
                    reasons.append(reason)

    severity_level = infer_table_severity_level(columns, rows)
    if not finding_levels or severity_level in {None, "ok"}:
        return severity_level, {}

    evaluation = planned.source_metadata.get("evaluation") or {}
    summary_title = str(
        evaluation.get("summary_title")
        or f"{planned.title}: review required"
    )
    description = (
        f"{len(finding_levels)} finding row(s); highest severity is {severity_level}."
    )
    if reasons:
        description += " " + "; ".join(reasons[:3])
        if len(reasons) > 3:
            description += f"; and {len(reasons) - 3} more reason(s)"
    recommendation = str(
        evaluation.get("recommendation")
        or "Review the finding rows and item instruction before changing production settings."
    )
    return severity_level, {
        "summary": {
            "severity": severity_level,
            "status": "fail" if severity_level == "high" else "review",
            "title": summary_title,
            "description": description,
            "recommendation": recommendation,
        },
        "items": [],
    }


def _classify_sql_error(exc: Exception, planned: PlannedEntry) -> str:
    name = exc.__class__.__name__
    if "FeatureNotSupported" in name:
        return "unsupported"
    if _is_missing_optional_source_shape(exc, planned):
        return "unsupported"
    return "error"


def _is_missing_optional_source_shape(exc: Exception, planned: PlannedEntry) -> bool:
    name = exc.__class__.__name__
    sqlstate = getattr(exc, "sqlstate", None)
    return bool(planned.source_metadata.get("optional")) and (
        "UndefinedTable" in name
        or "UndefinedColumn" in name
        or "UndefinedFunction" in name
        or sqlstate in {"42P01", "42703", "42883"}
    )


def _sql_exception_diagnostic(status: str, message: str, exc: BaseException) -> dict[str, Any]:
    level = "error" if status == "error" else "warning"
    return exception_diagnostic(status, message, exc, level=level)
