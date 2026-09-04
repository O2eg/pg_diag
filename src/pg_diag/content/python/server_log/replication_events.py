from __future__ import annotations

from typing import Any

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result
from pg_diag.logscan.items_common import (
    coverage_note,
    empty_result_status,
    fmt_time,
    resolve_english_window,
)

ROW_LIMIT = 100
_KINDS = (
    ("archive command failed", "archive_failure"),
    ("restore command failed", "restore_failure"),
    ("requested WAL segment", "wal_missing"),
    ("has already been removed", "wal_missing"),
    ("could not receive data from WAL stream", "walreceiver_disconnect"),
    ("terminating walreceiver", "walreceiver_disconnect"),
    ("could not send data to client", "walsender_disconnect"),
    ("could not receive data from client", "walsender_disconnect"),
    ("requested starting point", "stream_start_failure"),
    ("is not in this server's history", "timeline_mismatch"),
    ("requested timeline", "timeline_mismatch"),
    ("replication slot invalidated", "replication_slot"),
    ("invalidating obsolete replication slot", "replication_slot"),
    ("can no longer get changes from replication slot", "replication_slot"),
    ("cannot use replication slot", "replication_slot"),
    ("conflict with recovery", "recovery_conflict"),
)

_GENERIC_FAILURE_KINDS = (
    ("replication slot", "replication_slot"),
    ("logical replication", "logical_replication"),
    ("subscription", "logical_replication"),
)


def _kind(message: str, severity: str) -> str | None:
    lowered = message.lower()
    specific = next((kind for fragment, kind in _KINDS if fragment.lower() in lowered), None)
    if specific is not None:
        return specific
    if severity in {"WARNING", "ERROR", "FATAL", "PANIC"}:
        return next(
            (kind for fragment, kind in _GENERIC_FAILURE_KINDS if fragment in lowered),
            None,
        )
    return None


def collect(context: PythonSourceContext) -> PythonSourceResult:
    window, early = resolve_english_window(context)
    if early is not None:
        return PythonSourceResult(**early)
    events = [(record, _kind(record.message, record.severity)) for record in window.records]
    events = [(record, kind) for record, kind in events if kind]
    events.sort(key=lambda item: (item[0].repeat_count, item[0].last_time), reverse=True)
    omitted = max(0, len(events) - ROW_LIMIT)
    rows: list[dict[str, Any]] = [
        {
            "first_time": fmt_time(record.log_time),
            "last_time": fmt_time(record.last_time),
            "event_type": kind,
            "occurrences": record.repeat_count,
            "severity": record.severity,
            "sql_state": record.sql_state,
            "database_name": record.database_name,
            "application_name": record.application_name,
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
    description = f"{len(events)} replication event series matched; {len(rows)} are shown."
    if omitted:
        description += (
            f" {omitted} lower-ranked series were omitted by the fixed {ROW_LIMIT}-row limit."
        )
    if note:
        description += f" {note}"
    severity = "unknown" if note else "high"
    return PythonSourceResult(
        collection_status="ok",
        result=result,
        severity_level=severity,
        issues={
            "summary": {
                "severity": severity,
                "status": "review",
                "title": "Replication and WAL transport events need review",
                "description": description,
                "recommendation": "Check archive/restore commands, retained WAL, timelines, replication slots, receiver/sender connectivity, and logical replication workers.",
            },
            "items": [],
        },
    )
