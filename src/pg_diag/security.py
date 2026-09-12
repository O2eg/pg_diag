"""Redaction and JSON-safe value helpers."""

from __future__ import annotations

import math
import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

REDACTED = "[REDACTED]"

SENSITIVE_NAME_RE = re.compile(
    r"(password|passwd|secret|token|apikey|api_key|credential|dsn|conninfo)",
    re.IGNORECASE,
)

# Utility statements are not literal-normalized by pg_stat_statements. In
# particular, CREATE/ALTER SUBSCRIPTION can retain a full connection password.
_QUERY_CREDENTIAL_LITERAL_RE = re.compile(
    r"(?P<prefix>\b(?:PASSWORD|CONNECTION)(?:\s|/\*.*?\*/|--[^\n]*(?:\n|$))+)"
    r"(?:E'(?:''|\\.|[^'\\])*'|'(?:''|[^'])*'"
    r"|\$(?P<tag>[A-Za-z_][A-Za-z_0-9]*|)\$.*?\$(?P=tag)\$)",
    re.IGNORECASE | re.DOTALL,
)


def redact_query_credentials(value: str) -> str:
    """Hide password clauses and connection literals in retained SQL text."""
    return _QUERY_CREDENTIAL_LITERAL_RE.sub(
        lambda match: match.group("prefix") + f"'{REDACTED}'", value
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
        if value.tzinfo is None:
            return value.isoformat()
        return value.astimezone(timezone.utc).isoformat().removesuffix("+00:00") + "Z"
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


# "password=secret", "PGPASSWORD: x", "AWS_SECRET_ACCESS_KEY=..." -> the value is the
# secret. The key may embed the sensitive word anywhere in the identifier; the value is a
# quoted string or one whitespace-free token. Identifiers that merely contain the word
# and never carry a secret value (the GUCs password_encryption and passwordcheck.*) are
# the only exceptions.
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?P<key>(?<![\w.])(?!password_encryption\b|passwordcheck\b)"
    r"[\w.-]*?(?:password|passwd|secret|token|apikey|api_key|credential)[\w.-]*\s*[=:]\s*)"
    r"(?P<value>'[^']*'|\"[^\"]*\"|[^\s'\"]+)",
    re.IGNORECASE,
)
# A bare sensitive word as its own token (not part of an identifier such as
# password_encryption or passwordcheck) still hides the whole line.
_SENSITIVE_WORD_RE = re.compile(
    r"(?<![\w.])(password|passwd|secret|token|apikey|api_key|credential|dsn|conninfo)(?![\w])",
    re.IGNORECASE,
)


def redact_text(value: str) -> str:
    """Line-oriented redaction for script and plain-text output.

    Secret values in ``key=value`` / ``key: value`` form (quoted or bare) and
    credentials in connection URIs are replaced. A line that still names a
    secret outside such a pair is hidden entirely, even when another pair on the
    same line was already redacted. Identifiers that merely contain the word,
    such as the GUC ``password_encryption`` on a postmaster command line, are
    kept.
    """
    lines = []
    for line in value.splitlines():
        candidate = redact_dsn(line) or ""
        if any(_ambiguous_value(candidate, match) for match in _SECRET_ASSIGNMENT_RE.finditer(candidate)):
            # shell escapes or mixed quoting: the value's end cannot be located, hide everything
            lines.append(REDACTED)
            continue
        candidate = _SECRET_ASSIGNMENT_RE.sub(lambda m: m.group("key") + REDACTED, candidate)
        # Look for bare secret words in what is left after the handled pairs are removed.
        remainder = _SECRET_ASSIGNMENT_RE.sub("", candidate)
        if _SENSITIVE_WORD_RE.search(remainder):
            lines.append(REDACTED)
        else:
            lines.append(candidate)
    return "\n".join(lines)


def _ambiguous_value(line: str, match: "re.Match[str]") -> bool:
    """True when the matched secret value may continue past where the pattern stopped.

    A backslash inside the value (``prefix\\ rest``, ``"a\\"b"``) escapes the delimiter the
    pattern relied on, and a quote that opens right after a bare or quoted value
    (``abc'def ghi'``, ``'a'"b c"``) starts another segment of the same word. A quote that
    closes an enclosing string (``'host=db password=x'``) is not ambiguous.
    """
    value = match.group("value")
    if "\\" in value:
        return True
    following = line[match.end() : match.end() + 1]
    if following in ("'", '"'):
        return line[: match.start()].count(following) % 2 == 0
    return False


def redact_error(value: BaseException | str) -> str:
    text = str(value)
    text = redact_dsn(text) or ""
    if is_sensitive_name(text):
        return REDACTED
    return text
