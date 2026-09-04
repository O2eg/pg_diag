from __future__ import annotations

from typing import Any

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result
from pg_diag.logscan.items_common import (
    empty_result_status,
    fmt_time,
    message_contains_any,
    resolve_english_window,
)

EVENT_LIMIT = 200
_FRAGMENTS = (
    "terminated by signal",
    "was not properly shut down",
    "automatic recovery in progress",
    "redo starts at",
    "invalid page",
    "terminating any other active server processes",
)


def collect(context: PythonSourceContext) -> PythonSourceResult:
    window, early = resolve_english_window(context)
    if early is not None:
        return PythonSourceResult(**early)
    events = [record for record in window.records if message_contains_any(record, _FRAGMENTS)]
    truncated = len(events) > EVENT_LIMIT
    events = events[-EVENT_LIMIT:]
    rows: list[dict[str, Any]] = []
    for record in reversed(events):  # newest first
        rows.append(
            {
                "log_time": fmt_time(record.log_time),
                "severity": record.severity,
                "message": record.message,
                "repeat_count": record.repeat_count,
                "process_id": record.process_id,
                "backend_type": record.backend_type,
                "user_name": record.user_name,
                "database_name": record.database_name,
            }
        )
    severity_level = "high" if rows else "ok"
    issues: dict[str, Any] = {}
    if rows:
        issues = {
            "summary": {
                "severity": "high",
                "status": "fail",
                "title": "Crash, recovery, or corruption markers found in the server log",
                "description": (
                    f"{len(rows)} crash/recovery event(s) in the collected window."
                    + (" Older events beyond the limit are not listed." if truncated else "")
                ),
                "recommendation": (
                    "Treat 'terminated by signal' and 'invalid page' as incidents: identify "
                    "the crashed process, check for OOM kills and storage errors, and verify "
                    "the cluster completed recovery cleanly."
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
