from __future__ import annotations

from typing import Any

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result
from pg_diag.logscan.items_common import (
    SEVERITY_ERRORS,
    coverage_note,
    fmt_time,
    empty_result_status,
    resolve_english_window,
    severity_rank,
)

SERIES_LIMIT = 100


def collect(context: PythonSourceContext) -> PythonSourceResult:
    window, early = resolve_english_window(context)
    if early is not None:
        return PythonSourceResult(**early)
    series = [record for record in window.records if record.severity in SEVERITY_ERRORS]
    truncated = len(series) > SERIES_LIMIT
    series = series[-SERIES_LIMIT:]  # keep the newest series
    rows: list[dict[str, Any]] = []
    for record in reversed(series):  # newest first
        rows.append(
            {
                "first_time": fmt_time(record.log_time),
                "last_time": fmt_time(record.last_time),
                "repeat_count": record.repeat_count,
                "severity": record.severity,
                "sql_state": record.sql_state,
                "message": record.message,
                "user_name": record.user_name,
                "database_name": record.database_name,
                "process_id": record.process_id,
                "backend_type": record.backend_type,
                "query_id": record.query_id,
                "count_complete": record.count_complete,
                "partial": record.partial,
            }
        )
    worst = max((severity_rank(record.severity) for record in series), default=0)
    severity_level = "high" if worst >= 3 else ("medium" if rows else "ok")
    issues: dict[str, Any] = {}
    if rows:
        total = sum(record.repeat_count for record in series)
        note = coverage_note(window)
        description = (
            f"{len(rows)} error series ({total} raw records) in the collected window."
            + (f" Older series beyond the last {SERIES_LIMIT} are not listed." if truncated else "")
            + (f" {note}" if note else "")
        )
        issues = {
            "summary": {
                "severity": severity_level,
                "status": "fail" if worst >= 3 else "review",
                "title": "Server log contains error events",
                "description": description,
                "recommendation": (
                    "Read the chronology top-down: repeat_count folds floods of identical "
                    "errors into one series; investigate FATAL and PANIC entries first."
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
