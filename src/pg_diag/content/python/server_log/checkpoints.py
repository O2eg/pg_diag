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
_HEAD_RE = re.compile(r"^(checkpoint|restartpoint) (starting|complete)")
_REASON_RE = re.compile(r"(?:checkpoint|restartpoint) starting: (.+)$")
_BUFFERS_RE = re.compile(r"wrote (\d+) buffers")
_TIMING_RE = re.compile(r"write=(\d+(?:\.\d+)?) s, sync=(\d+(?:\.\d+)?) s, total=(\d+(?:\.\d+)?) s")


def collect(context: PythonSourceContext) -> PythonSourceResult:
    window, early = resolve_english_window(context)
    if early is not None:
        return PythonSourceResult(**early)
    events = []
    forced = 0
    for record in window.records:
        match = _HEAD_RE.search(record.message)
        if match is None:
            continue
        events.append((record, match.group(1), match.group(2)))
    matched_count = len(events)
    truncated = matched_count > EVENT_LIMIT
    events = events[-EVENT_LIMIT:]
    rows: list[dict[str, Any]] = []
    for record, event, phase in reversed(events):  # newest first
        reason_match = _REASON_RE.search(record.message)
        reason = reason_match.group(1) if reason_match else None
        if event == "checkpoint" and phase == "starting" and reason and "wal" in reason.split():
            forced += record.repeat_count
        buffers = _BUFFERS_RE.search(record.message)
        timing = _TIMING_RE.search(record.message)
        rows.append(
            {
                "log_time": fmt_time(record.log_time),
                "last_time": fmt_time(record.last_time),
                "event": event,
                "phase": phase,
                "reason": reason,
                "buffers_written": int(buffers.group(1)) if buffers else None,
                "write_s": float(timing.group(1)) if timing else None,
                "sync_s": float(timing.group(2)) if timing else None,
                "total_s": float(timing.group(3)) if timing else None,
                "repeat_count": record.repeat_count,
                "count_complete": record.count_complete,
            }
        )
    result = table_result(rows)
    inventory = getattr(getattr(context, "server_log", None), "inventory", None) or {}
    result.update(
        matched_series_count=matched_count,
        omitted_series_count=max(0, matched_count - EVENT_LIMIT),
        row_limit=EVENT_LIMIT,
        log_utc_offset_seconds=(inventory.get("settings") or {}).get("log_utc_offset_seconds"),
    )
    if not rows:
        status, empty_severity, empty_issues = empty_result_status(window)
        return PythonSourceResult(
            collection_status=status,
            result=result,
            issues=empty_issues,
            severity_level=empty_severity,
        )
    severity = "medium" if forced else "ok"
    issues: dict[str, Any] = {}
    if forced:
        issues = {
            "summary": {
                "severity": "medium",
                "status": "review",
                "title": "Checkpoints are triggered by WAL pressure",
                "description": (
                    f"{forced} checkpoint(s) in the window started for wal "
                    "reasons instead of the timed schedule."
                ),
                "recommendation": (
                    "Raise max_wal_size or investigate WAL spikes; frequent forced "
                    "checkpoints inflate I/O and recovery time variance."
                ),
            },
            "items": [],
        }
    elif truncated:
        issues = {
            "summary": {
                "severity": "ok",
                "status": "review",
                "title": "Only the newest checkpoint events are listed",
                "description": f"More than {EVENT_LIMIT} events matched the window.",
                "recommendation": "Narrow --log-depth-time-min for the full picture.",
            },
            "items": [],
        }
    return PythonSourceResult(
        collection_status="ok",
        result=result,
        issues=issues,
        severity_level=severity,
    )
