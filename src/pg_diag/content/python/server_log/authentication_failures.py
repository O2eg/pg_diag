from __future__ import annotations

from typing import Any

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result
from pg_diag.logscan.items_common import (
    client_host,
    coverage_note,
    fmt_time,
    message_contains_any,
    empty_result_status,
    resolve_window,
)

TOP_LIMIT = 100
_AUTH_SQLSTATES = {"28000", "28P01"}
_FRAGMENTS = ("password authentication failed", "no pg_hba.conf entry")


def collect(context: PythonSourceContext) -> PythonSourceResult:
    window, early = resolve_window(context)
    if early is not None:
        return PythonSourceResult(**early)
    groups: dict[tuple, dict[str, Any]] = {}
    for record in window.records:
        if record.sql_state not in _AUTH_SQLSTATES and not message_contains_any(
            record, _FRAGMENTS
        ):
            continue
        client = client_host(record.connection_from)
        key = (record.user_name, record.database_name, client, record.sql_state)
        group = groups.setdefault(
            key,
            {
                "user_name": record.user_name,
                "database_name": record.database_name,
                "connection_from": client,
                "sql_state": record.sql_state,
                "failures": 0,
                "count_complete": True,
                "first_seen": record.log_time,
                "last_seen": record.last_time,
                "message_sample": record.message,
            },
        )
        group["failures"] += record.repeat_count
        group["count_complete"] = group["count_complete"] and record.count_complete
        group["first_seen"] = min(group["first_seen"], record.log_time)
        group["last_seen"] = max(group["last_seen"], record.last_time)
    ordered = sorted(groups.values(), key=lambda g: (-g["failures"], g["first_seen"]))
    rows = [
        {
            "user_name": group["user_name"],
            "connection_from": group["connection_from"],
            "database_name": group["database_name"],
            "sql_state": group["sql_state"],
            "failures": group["failures"],
            "first_seen": fmt_time(group["first_seen"]),
            "last_seen": fmt_time(group["last_seen"]),
            "message_sample": group["message_sample"],
            "count_complete": group["count_complete"],
        }
        for group in ordered[:TOP_LIMIT]
    ]
    severity_level = "medium" if rows else "ok"
    issues: dict[str, Any] = {}
    if rows:
        note = coverage_note(window)
        issues = {
            "summary": {
                "severity": "medium",
                "status": "review",
                "title": "Authentication failures recorded in the server log",
                "description": (
                    f"{len(groups)} distinct (user, client, database) failure group(s)."
                    + (f" {note}" if note else "")
                ),
                "recommendation": (
                    "Repeated failures from one client suggest a misconfigured service or "
                    "credential rotation gone wrong; a wide spread of users and addresses "
                    "suggests scanning or brute force - check pg_hba.conf exposure."
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
