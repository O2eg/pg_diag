from __future__ import annotations

from typing import Any

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result
from pg_diag.logscan.items_common import (
    SEVERITY_ERRORS,
    coverage_note,
    fmt_time,
    empty_result_status,
    resolve_window,
    severity_rank,
)

TOP_LIMIT = 100


def collect(context: PythonSourceContext) -> PythonSourceResult:
    window, early = resolve_window(context)
    if early is not None:
        return PythonSourceResult(**early)
    groups: dict[tuple[str, str | None], dict[str, Any]] = {}
    for record in window.records:
        if record.severity not in SEVERITY_ERRORS:
            continue
        group = groups.setdefault(
            (record.fingerprint, record.sql_state),
            {
                "message_sample": record.message,
                "severity_worst": record.severity,
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
        if severity_rank(record.severity) > severity_rank(group["severity_worst"]):
            group["severity_worst"] = record.severity
        if record.user_name:
            group["users"].add(record.user_name)
        if record.database_name:
            group["databases"].add(record.database_name)
    ordered = sorted(groups.values(), key=lambda g: (-g["occurrences"], g["first_seen"]))
    rows = [
        {
            "message_sample": group["message_sample"],
            "severity_worst": group["severity_worst"],
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
    severity_level = "medium" if rows else "ok"
    issues: dict[str, Any] = {}
    note = coverage_note(window)
    if rows:
        title = "Errors grouped by normalized message"
        if note:
            title = "Top errors cover only part of the requested window"
        issues = {
            "summary": {
                "severity": severity_level,
                "status": "review",
                "title": title,
                "description": (
                    f"{len(groups)} distinct error fingerprints in the collected window."
                    + (f" {note}" if note else "")
                ),
                "recommendation": (
                    "Start with the most frequent fingerprints; occurrences are exact for "
                    "count_complete rows and lower bounds otherwise."
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
