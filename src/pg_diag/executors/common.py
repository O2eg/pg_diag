"""Shared executor result helpers."""

from __future__ import annotations

import traceback
import time
from pathlib import Path
from typing import Any

from pg_diag.security import json_safe, redact_row, redact_text


def read_source_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def table_result_from_records(records: list[Any] | tuple[Any, ...]) -> dict[str, Any]:
    normalized_records = [
        record if isinstance(record, dict) else {"value": record}
        for record in records
    ]
    columns = columns_from_records(normalized_records)
    rows = [row_from_record(columns, record) for record in normalized_records]
    return {"kind": "table", "columns": columns, "rows": rows, "row_count": len(rows)}


def columns_from_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    columns: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        for key in record:
            name = str(key)
            if name in seen:
                continue
            seen.add(name)
            values = [record.get(name) for record in records if record.get(name) is not None]
            columns.append(
                {
                    "name": name,
                    "pg_type": _inferred_pg_type(values),
                    "pg_type_oid": None,
                }
            )
    return columns


def _inferred_pg_type(values: list[Any]) -> str:
    if not values:
        return "json"
    if all(isinstance(value, bool) for value in values):
        return "bool"
    if all(isinstance(value, int) and not isinstance(value, bool) for value in values):
        return "int8"
    if all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in values
    ):
        return "float8"
    if all(isinstance(value, str) for value in values):
        return "text"
    return "json"


def row_from_record(columns: list[dict[str, Any]], record: dict[str, Any]) -> list[Any]:
    missing_indexes = set()
    row = []
    for index, column in enumerate(columns):
        name = column["name"]
        if name not in record:
            missing_indexes.add(index)
            row.append(None)
        else:
            row.append(json_safe(record.get(name)))
    redacted = redact_row(columns, row)
    for index in missing_indexes:
        redacted[index] = None
    return redacted


def exception_diagnostic(code: str, message: str, exc: BaseException, *, level: str = "error") -> dict[str, Any]:
    trace = redact_text("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    return {"level": level, "code": code, "message": message, "traceback": trace}


def elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)
