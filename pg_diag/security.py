"""Redaction and JSON-safe value helpers."""

from __future__ import annotations

import math
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

REDACTED = "[REDACTED]"

SENSITIVE_NAME_RE = re.compile(
    r"(password|passwd|secret|token|apikey|api_key|credential|dsn|conninfo)",
    re.IGNORECASE,
)


def is_sensitive_name(name: str | None) -> bool:
    return bool(name and SENSITIVE_NAME_RE.search(name))


def redact_dsn(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"(://[^:/@]+:)([^@]+)(@)", rf"\1{REDACTED}\3", value)


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, (list, tuple, set, frozenset)):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    return str(value)


def sanitize_public_structure(value: Any, field_name: str | None = None) -> Any:
    """Normalize extension-provided values and redact explicitly sensitive fields."""
    if field_name and is_sensitive_name(field_name):
        return REDACTED
    if isinstance(value, dict):
        return {
            str(key): sanitize_public_structure(item, str(key))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [sanitize_public_structure(item) for item in value]
    if isinstance(value, str) and field_name in {"traceback", "stdout", "stderr", "output"}:
        return redact_text(value)
    return json_safe(value)


def sanitize_result(result: dict[str, Any] | None) -> dict[str, Any]:
    normalized = sanitize_public_structure(result or {"kind": "none"})
    if not isinstance(normalized, dict):
        return {"kind": "none"}

    kind = normalized.get("kind", "none")
    if kind == "plain_text":
        normalized["data"] = redact_text(str(normalized.get("data") or ""))
    elif kind == "table":
        raw_columns = normalized.get("columns") or []
        rows = normalized.get("rows") or []
        if isinstance(raw_columns, list) and isinstance(rows, list):
            columns = [_normalize_column(column, index) for index, column in enumerate(raw_columns)]
            normalized["columns"] = columns
            normalized["rows"] = [
                redact_row(columns, _normalize_row(row, columns)) for row in rows
            ]
            normalized["row_count"] = len(normalized["rows"])
    return normalized


def redact_row(columns: list[Any], row: list[Any]) -> list[Any]:
    redacted: list[Any] = []
    column_names = [_column_name(column, index) for index, column in enumerate(columns)]
    name_to_index = {name: index for index, name in enumerate(column_names)}
    setting_name = None
    for name in ("name", "tag_setting_name", "setting_name"):
        index = name_to_index.get(name)
        if index is not None and index < len(row):
            setting_name = str(row[index])
            break

    for index, value in enumerate(row):
        column_name = column_names[index] if index < len(column_names) else ""
        if is_sensitive_name(column_name):
            redacted.append(REDACTED)
            continue
        if column_name in {"setting", "tag_setting_value", "setting_value", "effective_setting"}:
            if is_sensitive_name(setting_name):
                redacted.append(REDACTED)
                continue
        if isinstance(value, str) and is_sensitive_name(column_name):
            redacted.append(REDACTED)
            continue
        redacted.append(json_safe(value))
    return redacted


def _normalize_column(column: Any, index: int) -> dict[str, Any]:
    if isinstance(column, dict):
        normalized = dict(column)
        normalized["name"] = _column_name(column, index)
        return normalized
    return {"name": _column_name(column, index)}


def _column_name(column: Any, index: int) -> str:
    if isinstance(column, dict):
        value = column.get("name")
    else:
        value = column
    text = str(value or "").strip()
    return text or f"column_{index + 1}"


def _normalize_row(row: Any, columns: list[dict[str, Any]]) -> list[Any]:
    if isinstance(row, dict):
        return [row.get(column["name"]) for column in columns]
    if isinstance(row, (list, tuple)):
        return list(row)
    return [row]


def redact_text(value: str) -> str:
    # Conservative line-level redaction for script/plain text output.
    lines = []
    for line in value.splitlines():
        if is_sensitive_name(line):
            lines.append(REDACTED)
        else:
            lines.append(line)
    return "\n".join(lines)


def redact_error(value: BaseException | str) -> str:
    text = str(value)
    text = redact_dsn(text) or ""
    if is_sensitive_name(text):
        return REDACTED
    return text
