from __future__ import annotations

from typing import Any

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result
from pg_diag.logscan.items_common import (
    empty_result_status,
    fmt_time,
    resolve_window,
)

EVENT_LIMIT = 100
_DEADLOCK_SQLSTATE = "40P01"


def collect(context: PythonSourceContext) -> PythonSourceResult:
    window, early = resolve_window(context)
    if early is not None:
        return PythonSourceResult(**early)
    events = [record for record in window.records if record.sql_state == _DEADLOCK_SQLSTATE]
    events = events[-EVENT_LIMIT:]
    rows: list[dict[str, Any]] = []
    for record in reversed(events):  # newest first
        rows.append(
            {
                "log_time": fmt_time(record.log_time),
                "database_name": record.database_name,
                "user_name": record.user_name,
                "process_id": record.process_id,
                "repeat_count": record.repeat_count,
                "message": record.message,
                "query_id": record.query_id,
            }
        )
    severity_level = "medium" if rows else "ok"
    issues: dict[str, Any] = {}
    if rows:
        issues = {
            "summary": {
                "severity": "medium",
                "status": "review",
                "title": "Deadlocks were detected during the window",
                "description": f"{len(rows)} deadlock event(s) in the collected window.",
                "recommendation": (
                    "Deadlocks are application-ordering bugs: make transactions lock objects "
                    "in a consistent order; message text names the sessions involved."
                ),
            },
            "items": [],
        }
    if not rows:
        status, empty_severity, empty_issues = empty_result_status(window)
        return PythonSourceResult(
            collection_status=status,
            result=table_result(rows),
            issues=empty_issues,
            severity_level=empty_severity,
        )
    return PythonSourceResult(
        collection_status="ok",
        result=table_result(rows),
        issues=issues,
        severity_level=severity_level,
    )
