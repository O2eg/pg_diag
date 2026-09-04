from __future__ import annotations

from typing import Any

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result
from pg_diag.logscan.items_common import (
    empty_result_status,
    fmt_time,
    message_contains_any,
    resolve_english_window,
)

EVENT_LIMIT = 100
_FRAGMENTS = ("archive command failed",)


def collect(context: PythonSourceContext) -> PythonSourceResult:
    window, early = resolve_english_window(context)
    if early is not None:
        return PythonSourceResult(**early)
    events = [record for record in window.records if message_contains_any(record, _FRAGMENTS)]
    events = events[-EVENT_LIMIT:]
    rows: list[dict[str, Any]] = []
    total = 0
    for record in reversed(events):  # newest first
        total += record.repeat_count
        rows.append(
            {
                "first_time": fmt_time(record.log_time),
                "last_time": fmt_time(record.last_time),
                "repeat_count": record.repeat_count,
                "severity": record.severity,
                "message": record.message,
                "count_complete": record.count_complete,
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
            "title": "WAL archiving is failing",
            "description": (
                f"{total} failed archive_command invocation(s) in the collected "
                "window. Un-archived WAL accumulates in pg_wal and the WAL archive "
                "has a gap."
            ),
            "recommendation": (
                "Fix archive_command (the sanitized message shows its output), then "
                "confirm pg_stat_archiver.failed_count stops growing and pg_wal "
                "drains; verify PITR coverage over the gap."
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
