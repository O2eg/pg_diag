from __future__ import annotations

from typing import Any

from pg_diag.logscan.query_links import group_query_columns, remember_group_query

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result
from pg_diag.logscan.items_common import (
    SEVERITY_ERRORS,
    coverage_note,
    fmt_time,
    empty_result_status,
    resolve_english_window,
    severity_rank,
)

TOP_LIMIT = 100
DEFAULT_DISTINCT_NAMES_LIMIT = 30


def collect(context: PythonSourceContext) -> PythonSourceResult:
    window, early = resolve_english_window(context)
    if early is not None:
        return PythonSourceResult(**early)
    settings = (getattr(context, "source", None) or {}).get("settings", {})
    names_limit = settings.get("distinct_names_limit", DEFAULT_DISTINCT_NAMES_LIMIT)
    if isinstance(names_limit, bool) or not isinstance(names_limit, int) or names_limit < 1:
        raise ValueError("settings.distinct_names_limit must be a positive integer")
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
        remember_group_query(group, record)
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
            **group_query_columns(group),
            "severity_worst": group["severity_worst"],
            "sql_state": group["sql_state"],
            "occurrences": group["occurrences"],
            "first_seen": fmt_time(group["first_seen"]),
            "last_seen": fmt_time(group["last_seen"]),
            "distinct_users": sorted(group["users"])[:names_limit],
            "distinct_databases": sorted(group["databases"])[:names_limit],
        }
        for group in ordered[:TOP_LIMIT]
    ]
    result = table_result(rows)
    matched = sum(group["occurrences"] for group in ordered)
    displayed = sum(row["occurrences"] for row in rows)
    result.update(
        matched_event_count=matched, displayed_event_count=displayed,
        omitted_event_count=matched - displayed, aggregate_count=len(ordered),
        omitted_aggregate_count=max(0, len(ordered) - TOP_LIMIT), row_limit=TOP_LIMIT,
    )
    omitted_users = sum(max(0, len(group["users"]) - names_limit) for group in ordered[:TOP_LIMIT])
    omitted_databases = sum(
        max(0, len(group["databases"]) - names_limit) for group in ordered[:TOP_LIMIT]
    )
    result.update(
        distinct_names_limit=names_limit,
        omitted_user_name_count=omitted_users,
        omitted_database_name_count=omitted_databases,
        count_complete=window.coverage.ranking_complete and all(
            group["count_complete"] for group in ordered
        ),
    )
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
                    + (
                        f" Identity lists show at most {names_limit} names per group; "
                        f"{omitted_users} user names and {omitted_databases} database names "
                        "were omitted across the displayed groups."
                        if omitted_users or omitted_databases else ""
                    )
                    + (f" {note}" if note else "")
                ),
                "recommendation": (
                    "Start with the most frequent fingerprints and inspect the affected users "
                    "and databases. Counts cover collected records; incomplete collection "
                    "provides lower bounds."
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
