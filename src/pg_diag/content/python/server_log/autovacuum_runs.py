from __future__ import annotations

import re
from typing import Any

from pg_diag.logscan.query_links import query_columns

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result
from pg_diag.logscan.items_common import (
    empty_result_status,
    event_count_metadata,
    fmt_time,
    resolve_english_window,
)

EVENT_LIMIT = 200
_HEAD_RE = re.compile(
    r"automatic (?P<aggressive>aggressive )?(?P<kind>vacuum|analyze) of table \"(?P<relation>[^\"]+)\""
)
_ELAPSED_RE = re.compile(r"elapsed: (\d+(?:\.\d+)?) s")


def collect(context: PythonSourceContext) -> PythonSourceResult:
    window, early = resolve_english_window(context)
    if early is not None:
        return PythonSourceResult(**early)
    events = []
    for record in window.records:
        message = record.message_full or record.message
        match = _HEAD_RE.search(message)
        if match is None:
            continue
        elapsed = _ELAPSED_RE.search(message)
        events.append(
            (record, match.group("kind"), match.group("aggressive") is not None, match.group("relation"), elapsed)
        )
    truncated = len(events) > EVENT_LIMIT
    counts = event_count_metadata(
        [event[0] for event in events],
        [event[0] for event in events[-EVENT_LIMIT:]], EVENT_LIMIT,
    )
    events = events[-EVENT_LIMIT:]
    rows: list[dict[str, Any]] = []
    for record, kind, aggressive, relation, elapsed in reversed(events):  # newest first
        rows.append(
            {
                "log_time": fmt_time(record.log_time),
                "kind": kind,
                # aggressive (anti-wraparound) vacuum freezes every page; it is the run a DBA
                # looks for when xid age is high
                "aggressive": aggressive,
                "relation": relation,
                "elapsed_s": float(elapsed.group(1)) if elapsed else None,
                "database_name": record.database_name,
                "repeat_count": record.repeat_count,
                "detail": record.message,
                **query_columns(record),
            }
        )
    result = table_result(rows)
    result.update(counts)
    if not rows:
        status, empty_severity, empty_issues = empty_result_status(window)
        return PythonSourceResult(
            collection_status=status,
            result=result,
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
                "description": (f"{counts['matched_event_count']} runs matched; "
                                f"{counts['omitted_event_count']} omitted by the row limit."),
                "recommendation": "Narrow --log-depth-time-min for the full picture.",
            },
            "items": [],
        }
    return PythonSourceResult(
        collection_status="ok",
        result=result,
        issues=issues,
        severity_level="ok",
    )
