from __future__ import annotations

import re
from typing import Any

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result
from pg_diag.logscan.items_common import (
    empty_result_status,
    fmt_time,
    message_contains_any,
    resolve_english_window,
)

EVENT_LIMIT = 100
_FRAGMENTS = ("must be vacuumed within", "is not accepting commands")
_DATABASE_RE = re.compile(r'database "(?P<database>[^"]+)"')
_REMAINING_RE = re.compile(r"within (\d+) transactions")


def collect(context: PythonSourceContext) -> PythonSourceResult:
    window, early = resolve_english_window(context)
    if early is not None:
        return PythonSourceResult(**early)
    events = [record for record in window.records if message_contains_any(record, _FRAGMENTS)]
    events = events[-EVENT_LIMIT:]
    stop_stage = any("is not accepting commands" in record.message for record in events)
    rows: list[dict[str, Any]] = []
    for record in reversed(events):  # newest first
        database = _DATABASE_RE.search(record.message)
        remaining = _REMAINING_RE.search(record.message)
        rows.append(
            {
                "first_time": fmt_time(record.log_time),
                "last_time": fmt_time(record.last_time),
                "repeat_count": record.repeat_count,
                "severity": record.severity,
                "database": database.group("database") if database else None,
                "transactions_left": int(remaining.group(1)) if remaining else None,
                "message": record.message,
            }
        )
    if not rows:
        status, empty_severity, empty_issues = empty_result_status(window)
        return PythonSourceResult(
            collection_status=status,
            result=table_result(rows),
            issues=empty_issues,
            severity_level=empty_severity,
        )
    issues = {
        "summary": {
            "severity": "high",
            "status": "fail",
            "title": (
                "Transaction ID wraparound protection is refusing commands"
                if stop_stage
                else "Transaction ID wraparound pressure is building"
            ),
            "description": (
                f"{len(rows)} wraparound warning group(s) in the collected window; "
                "these messages otherwise drown among ordinary warnings."
            ),
            "recommendation": (
                "Run an aggressive VACUUM in the named databases now and find what "
                "holds xmin (long transactions, abandoned replication slots, "
                "prepared transactions)."
            ),
        },
        "items": [],
    }
    return PythonSourceResult(
        collection_status="ok",
        result=table_result(rows),
        issues=issues,
        severity_level="high",
    )
