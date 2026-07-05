"""Redaction and JSON-safe value helpers."""

from __future__ import annotations

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
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
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
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    return str(value)


def redact_row(columns: list[dict[str, Any]], row: list[Any]) -> list[Any]:
    redacted: list[Any] = []
    name_to_index = {column["name"]: index for index, column in enumerate(columns)}
    setting_name = None
    for name in ("name", "tag_setting_name", "setting_name"):
        index = name_to_index.get(name)
        if index is not None and index < len(row):
            setting_name = str(row[index])
            break

    for index, value in enumerate(row):
        column_name = columns[index]["name"] if index < len(columns) else ""
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
