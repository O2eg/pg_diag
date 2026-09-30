from __future__ import annotations

import re
from typing import Any

from pg_diag.logscan.query_links import query_columns

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result
from pg_diag.logscan.items_common import (
    coverage_note,
    empty_result_status,
    event_count_metadata,
    fmt_time,
    resolve_english_window,
)

EVENT_LIMIT = 200
HIGH_ACCESS_EXCLUSIVE_MS = 10_000.0
HIGH_ANY_MS = 60_000.0

_HEAD_RE = re.compile(
    r"^process (?P<pid>\d+) "
    r"(?P<event>still waiting for|acquired|detected deadlock while waiting for) "
    r"(?P<lock_type>\w+) on (?P<target>.+?) after (?P<ms>\d+(?:\.\d+)?) ms"
)
_RELATION_RE = re.compile(r"relation (?P<relation>\d+) of database (?P<database>\d+)")
_DETAIL_RE = re.compile(
    r"Process(?:es)? holding the lock: (?P<holders>[\d, ]+)\. " r"Wait queue: (?P<queue>[\d, ]+)\."
)
_EVENT_NAMES = {
    "still waiting for": "waiting",
    "acquired": "acquired",
    "detected deadlock while waiting for": "deadlock_detected",
}


def _target_kind(target: str) -> str:
    return target.split(" ", 1)[0]


def collect(context: PythonSourceContext) -> PythonSourceResult:
    window, early = resolve_english_window(context)
    if early is not None:
        return PythonSourceResult(**early)
    events = []
    for record in window.records:
        match = _HEAD_RE.match(record.message)
        if match is None:
            continue
        events.append((record, match))
    truncated = len(events) > EVENT_LIMIT
    rows: list[dict[str, Any]] = []
    waiting = 0
    acquired = 0
    deadlock_context = 0
    max_wait_ms = 0.0
    severity = "medium"  # every matched row already exceeded deadlock_timeout
    lock_type_counts: dict[str, int] = {}
    for record, match in events:
        event = _EVENT_NAMES[match.group("event")]
        lock_type = match.group("lock_type")
        wait_ms = float(match.group("ms"))
        if event == "waiting":
            waiting += record.repeat_count
        elif event == "acquired":
            acquired += record.repeat_count
        else:
            deadlock_context += record.repeat_count
        max_wait_ms = max(max_wait_ms, wait_ms)
        lock_type_counts[lock_type] = lock_type_counts.get(lock_type, 0) + record.repeat_count
        if wait_ms > HIGH_ANY_MS or (
            lock_type == "AccessExclusiveLock" and wait_ms > HIGH_ACCESS_EXCLUSIVE_MS
        ):
            severity = "high"

    for record, match in reversed(events[-EVENT_LIMIT:]):  # newest first
        event = _EVENT_NAMES[match.group("event")]
        lock_type = match.group("lock_type")
        wait_ms = float(match.group("ms"))
        target = match.group("target")
        relation = _RELATION_RE.search(target)
        holders = None
        queue_depth = None
        if record.detail:
            detail_match = _DETAIL_RE.search(record.detail)
            if detail_match:
                holders = detail_match.group("holders").strip()
                queue_depth = len(
                    [pid for pid in detail_match.group("queue").split(",") if pid.strip()]
                )
        rows.append(
            {
                "first_time": fmt_time(record.log_time),
                "last_time": fmt_time(record.last_time),
                "repeat_count": record.repeat_count,
                "event": event,
                "waiting_pid": int(match.group("pid")),
                "lock_type": lock_type,
                "target_kind": _target_kind(target),
                "relation_oid": int(relation.group("relation")) if relation else None,
                "database_oid": int(relation.group("database")) if relation else None,
                "wait_ms": wait_ms,
                "holder_pids": holders,
                "queue_depth": queue_depth,
                "user_name": record.user_name,
                "database_name": record.database_name,
                **query_columns(record),
                "count_complete": record.count_complete,
            }
        )
    result = table_result(rows)
    result.update(event_count_metadata(
        [record for record, _ in events],
        [record for record, _ in events[-EVENT_LIMIT:]], EVENT_LIMIT,
    ))
    result.update(waiting_event_count=waiting, acquired_event_count=acquired,
                  deadlock_context_event_count=deadlock_context, max_wait_ms=max_wait_ms)
    if not rows:
        status, empty_severity, empty_issues = empty_result_status(window)
        return PythonSourceResult(
            collection_status=status,
            result=result,
            issues=empty_issues,
            severity_level=empty_severity,
        )
    dominant = max(lock_type_counts, key=lock_type_counts.get)
    note = coverage_note(window)
    issues = {
        "summary": {
            "severity": severity,
            "status": "fail" if severity == "high" else "review",
            "title": (
                "Long lock waits blocked sessions during the window"
                if severity == "high"
                else "Lock waits longer than deadlock_timeout were recorded"
            ),
            "description": (
                f"{waiting} waiting and {acquired} acquired event(s); the longest wait "
                f"is {max_wait_ms:.0f} ms and {dominant} dominates the conflicts. "
                f"{deadlock_context} supplemental deadlock wait event(s); these are context "
                "for SQLSTATE 40P01 events, not additional deadlock incidents. "
                "A 'waiting' event without a matching 'acquired' one was either "
                "cancelled or still waiting when the record was written."
                + (
                    f" Only the newest {EVENT_LIMIT} matching log records are listed."
                    if truncated
                    else ""
                )
                + (f" {note}" if note else "")
            ),
            "recommendation": (
                "Read holder_pids and queue_depth to find the blocking session; "
                "relation oids are clickable when DDL extraction ran. Compare with "
                "the live blocking lock tree collected at report time."
            ),
        },
        "items": [],
    }
    return PythonSourceResult(
        collection_status="ok",
        result=result,
        issues=issues,
        severity_level=severity,
    )
