from __future__ import annotations

import re
from typing import Any

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result
from pg_diag.logscan.items_common import (
    empty_result_status,
    fmt_time,
    resolve_english_window,
)

EVENT_LIMIT = 200
_HEAD_RE = re.compile(r"automatic (vacuum|analyze) of table \"(?P<relation>[^\"]+)\"")
_ELAPSED_RE = re.compile(r"elapsed: (\d+(?:\.\d+)?) s")


def collect(context: PythonSourceContext) -> PythonSourceResult:
    window, early = resolve_english_window(context)
    if early is not None:
        return PythonSourceResult(**early)
    events = []
    for record in window.records:
        match = _HEAD_RE.search(record.message)
        if match is None:
            continue
        elapsed = _ELAPSED_RE.search(record.message)
        events.append((record, match.group(1), match.group("relation"), elapsed))
    truncated = len(events) > EVENT_LIMIT
    events = events[-EVENT_LIMIT:]
    rows: list[dict[str, Any]] = []
    for record, kind, relation, elapsed in reversed(events):  # newest first
        rows.append(
            {
                "log_time": fmt_time(record.log_time),
                "kind": kind,
                "relation": relation,
                "elapsed_s": float(elapsed.group(1)) if elapsed else None,
                "database_name": record.database_name,
                "repeat_count": record.repeat_count,
                "detail": record.message,
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
    issues: dict[str, Any] = {}
    if truncated:
        issues = {
            "summary": {
                "severity": "ok",
                "status": "review",
                "title": "Only the newest autovacuum runs are listed",
                "description": f"More than {EVENT_LIMIT} runs matched the window.",
                "recommendation": "Narrow --log-depth-time-min for the full picture.",
            },
            "items": [],
        }
    return PythonSourceResult(
        collection_status="ok",
        result=table_result(rows),
        issues=issues,
        severity_level="ok",
    )
