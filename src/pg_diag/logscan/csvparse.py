"""CSV log record parsing on the collector (plan §4 phase 4, §15.5).

Input is one raw physical line: the first line of a possibly multiline csvlog
record. An unterminated quoted field therefore yields fewer columns than the
server major promises; such records are marked ``partial`` instead of failing.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime

_BASE_COLUMNS = (
    "log_time",
    "user_name",
    "database_name",
    "process_id",
    "connection_from",
    "session_id",
    "session_line_num",
    "command_tag",
    "session_start_time",
    "virtual_transaction_id",
    "transaction_id",
    "error_severity",
    "sql_state_code",
    "message",
    "detail",
    "hint",
    "internal_query",
    "internal_query_pos",
    "context",
    "query",
    "query_pos",
    "location",
    "application_name",
)


def expected_columns(server_version_num: int) -> int:
    if server_version_num >= 140000:
        return 26  # + backend_type, leader_pid, query_id
    if server_version_num >= 130000:
        return 24  # + backend_type
    return 23


@dataclass(frozen=True)
class ParsedRecord:
    log_time: datetime | None
    severity: str | None
    sql_state: str | None
    message: str | None
    detail: str | None
    user_name: str | None
    database_name: str | None
    process_id: int | None
    connection_from: str | None
    backend_type: str | None
    query_id: int | None
    partial: bool
    encoding_degraded: bool


def parse_timestamp(value: str) -> datetime | None:
    """Parse a csvlog log_time; the timezone suffix is dropped (log_timezone
    is constant per server run, comparisons stay within one zone)."""
    head, _, tail = value.rpartition(" ")
    candidate = head if head and any(ch.isalpha() for ch in tail) else value
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(candidate, fmt)
        except ValueError:
            continue
    return None


def parse_record(
    raw: bytes,
    *,
    server_version_num: int,
    encoding: str = "utf-8",
) -> ParsedRecord | None:
    """Parse one raw first-line of a csvlog record; None if it is no record."""
    degraded = False
    try:
        text = raw.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        text = raw.decode("utf-8", errors="replace")
        degraded = True
    try:
        fields = next(csv.reader(io.StringIO(text)))
    except (csv.Error, StopIteration):
        return None
    expected = expected_columns(server_version_num)
    partial = len(fields) < expected
    if len(fields) < 14:  # log_time..message is the minimum useful prefix
        return None
    log_time = parse_timestamp(fields[0])
    if log_time is None:
        return None

    def _get(index: int) -> str | None:
        if index < len(fields) and fields[index] != "":
            return fields[index]
        return None

    def _int(value: str | None) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    backend_type = _get(23) if server_version_num >= 130000 else None
    query_id = _int(_get(25)) if server_version_num >= 140000 else None
    return ParsedRecord(
        log_time=log_time,
        severity=_get(11),
        sql_state=_get(12),
        message=_get(13),
        detail=_get(14),
        user_name=_get(1),
        database_name=_get(2),
        process_id=_int(_get(3)),
        connection_from=_get(4),
        backend_type=backend_type,
        query_id=query_id,
        partial=partial,
        encoding_degraded=degraded,
    )
