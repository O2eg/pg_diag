from __future__ import annotations

from typing import Any

from pg_diag.logscan.query_links import query_columns

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result
from pg_diag.logscan.items_common import (
    coverage_note,
    empty_result_status,
    event_count_metadata,
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
    counts = event_count_metadata(events, events[-EVENT_LIMIT:], EVENT_LIMIT)
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
                # csvlog DETAIL names the blocked/blocking processes and their lock waits
                "detail": record.detail,
                **query_columns(record),
            }
        )
    result = table_result(rows)
    result.update(counts)
    note = coverage_note(window)
    severity_level = "unknown" if note else "medium" if rows else "ok"
    issues: dict[str, Any] = {}
    if rows:
        issues = {
            "summary": {
                "severity": severity_level,
                "status": "review",
                "title": "Deadlocks were detected during the window",
                "description": (
                    f"{counts['matched_event_count']} deadlock event(s) in the collected window; "
                    f"{len(rows)} series containing {counts['displayed_event_count']} events "
                    f"are shown; {counts['omitted_event_count']} events omitted by the "
                    f"{EVENT_LIMIT}-row limit."
                    + (f" {note}" if note else "")
                ),
                "recommendation": (
                    "Deadlocks are application-ordering bugs: make transactions lock objects "
                    "in a consistent order; the detail column names the sessions involved."
                ),
            },
            "items": [],
        }
    if not rows:
        status, empty_severity, empty_issues = empty_result_status(window)
        return PythonSourceResult(
            collection_status=status,
            result=result,
            issues=empty_issues,
            severity_level=empty_severity,
        )
    return PythonSourceResult(
        collection_status="ok",
        result=result,
        issues=issues,
        severity_level=severity_level,
    )
