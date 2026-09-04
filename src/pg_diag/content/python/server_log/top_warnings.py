from __future__ import annotations

from typing import Any

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result
from pg_diag.logscan.items_common import (
    empty_result_status,
    coverage_note,
    fmt_time,
    resolve_english_window,
)

TOP_LIMIT = 100


def collect(context: PythonSourceContext) -> PythonSourceResult:
    window, early = resolve_english_window(context)
    if early is not None:
        return PythonSourceResult(**early)
    groups: dict[tuple[str, str | None], dict[str, Any]] = {}
    for record in window.records:
        if record.severity != "WARNING":
            continue
        group = groups.setdefault(
            (record.fingerprint, record.sql_state),
            {
                "message_sample": record.message,
                "sql_state": record.sql_state,
                "occurrences": 0,
                "count_complete": True,
                "first_seen": record.log_time,
                "last_seen": record.last_time,
                "users": set(),
                "databases": set(),
            },
        )
        group["occurrences"] += record.repeat_count
        group["count_complete"] = group["count_complete"] and record.count_complete
        group["first_seen"] = min(group["first_seen"], record.log_time)
        group["last_seen"] = max(group["last_seen"], record.last_time)
        if record.user_name:
            group["users"].add(record.user_name)
        if record.database_name:
            group["databases"].add(record.database_name)
    ordered = sorted(groups.values(), key=lambda g: (-g["occurrences"], g["first_seen"]))
    rows = [
        {
            "message_sample": group["message_sample"],
            "sql_state": group["sql_state"],
            "occurrences": group["occurrences"],
            "first_seen": fmt_time(group["first_seen"]),
            "last_seen": fmt_time(group["last_seen"]),
            "distinct_users": len(group["users"]),
            "distinct_databases": len(group["databases"]),
            "count_complete": group["count_complete"],
        }
        for group in ordered[:TOP_LIMIT]
    ]
    issues: dict[str, Any] = {}
    note = coverage_note(window)
    if rows and note:
        issues = {
            "summary": {
                "severity": "ok",
                "status": "review",
                "title": "Top warnings cover only part of the requested window",
                "description": note,
                "recommendation": "Treat occurrences as lower bounds.",
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
        severity_level="ok",
    )
