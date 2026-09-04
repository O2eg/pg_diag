from __future__ import annotations

from typing import Any

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result
from pg_diag.logscan.items_common import (
    coverage_note,
    empty_result_status,
    fmt_time,
    is_recovery_end_of_wal,
    resolve_english_window,
)

ROW_LIMIT = 100
_KINDS = (
    ("database system is ready to accept", "ready"),
    ("database system is shut down", "shutdown_complete"),
    ("received fast shutdown request", "shutdown_fast"),
    ("received immediate shutdown request", "shutdown_immediate"),
    ("received smart shutdown request", "shutdown_smart"),
    ("starting PostgreSQL", "startup"),
    ("was not properly shut down", "unclean_shutdown"),
    ("automatic recovery in progress", "crash_recovery"),
    ("redo starts at", "recovery_redo"),
    ("redo done at", "recovery_complete"),
    ("selected new timeline ID", "promotion"),
    ("received promote request", "promotion"),
    ("reloading configuration files", "configuration_reload"),
    ("configuration file contains errors", "configuration_error"),
    ("terminated by signal", "backend_crash"),
    ("terminating any other active server processes", "backend_crash_cleanup"),
    ("could not create any TCP/IP sockets", "startup_failure"),
    ("could not bind", "startup_failure"),
    ("FATAL:  lock file", "startup_failure"),
)


def _kind(message: str) -> str | None:
    lowered = message.lower()
    return next((kind for fragment, kind in _KINDS if fragment.lower() in lowered), None)


def collect(context: PythonSourceContext) -> PythonSourceResult:
    window, early = resolve_english_window(context)
    if early is not None:
        return PythonSourceResult(**early)
    events = [
        (record, "recovery_wal_end" if is_recovery_end_of_wal(record) else _kind(record.message))
        for record in window.records
    ]
    events = [(record, kind) for record, kind in events if kind]
    events.sort(key=lambda item: item[0].last_time, reverse=True)
    omitted = max(0, len(events) - ROW_LIMIT)
    rows: list[dict[str, Any]] = [
        {
            "first_time": fmt_time(record.log_time),
            "last_time": fmt_time(record.last_time),
            "event_type": kind,
            "occurrences": record.repeat_count,
            "severity": record.severity,
            "sql_state": record.sql_state,
            "process_id": record.process_id,
            "backend_type": record.backend_type,
            "message": record.message,
            "count_complete": record.count_complete,
        }
        for record, kind in events[:ROW_LIMIT]
    ]
    result = table_result(rows)
    result.update(
        {
            "matched_series_count": len(events),
            "omitted_series_count": omitted,
            "row_limit": ROW_LIMIT,
        }
    )
    if not rows:
        status, severity, issues = empty_result_status(window)
        return PythonSourceResult(
            collection_status=status, result=result, issues=issues, severity_level=severity
        )
    note = coverage_note(window)
    critical = any(
        kind in {"unclean_shutdown", "backend_crash", "startup_failure", "configuration_error"}
        for _, kind in events
    )
    details = f"{len(events)} lifecycle series matched; {len(rows)} are shown."
    if omitted:
        details += f" {omitted} older series were omitted by the fixed {ROW_LIMIT}-row limit."
    if note:
        details += f" {note}"
    severity = "unknown" if note else ("high" if critical else "ok")
    return PythonSourceResult(
        collection_status="ok",
        result=result,
        severity_level=severity,
        issues={
            "summary": {
                "severity": severity,
                "status": "review" if critical or note else "ok",
                "title": "Server lifecycle events were recorded",
                "description": details,
                "recommendation": "Correlate unexpected shutdown, crash recovery, promotion, readiness, and configuration reload markers with the incident timeline.",
            },
            "items": [],
        },
    )
