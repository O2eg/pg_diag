from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result
from pg_diag.logscan.items_common import (
    coverage_note,
    empty_result_status,
    fmt_time,
    resolve_english_window,
)

ROW_LIMIT = 100
DURATION_SECONDS_THRESHOLD = 5.0
PAGE_BYTES_THRESHOLD = 128 * 1_048_576
BUFFER_BYTES_THRESHOLD = 128 * 1_048_576
WAL_BYTES_THRESHOLD = 64 * 1_048_576

_AUTO_HEAD_RE = re.compile(
    r'automatic (?P<kind>vacuum|analyze) of table "(?P<relation>[^"]+)"', re.I
)
_ELAPSED_RE = re.compile(r"elapsed:\s*(\d+(?:\.\d+)?)\s*s", re.I)
_DURATION_MS_RE = re.compile(r"^duration:\s*(\d+(?:\.\d+)?)\s*ms", re.I)
_LOCK_WAIT_MS_RE = re.compile(
    r"\b(?:still waiting for|acquired)\b.*?\bafter\s+(\d+(?:\.\d+)?)\s*ms",
    re.I,
)
_PAGES_RE = re.compile(
    r"pages:\s*(?P<removed>\d+)\s+removed,\s*(?P<remain>\d+)\s+remain"
    r"(?:,\s*(?P<scanned>\d+)\s+scanned)?",
    re.I,
)
_BUFFER_RE = re.compile(r"buffer usage:\s*(\d+)\s+hits,\s*(\d+)\s+misses,\s*(\d+)\s+dirtied", re.I)
_WAL_RE = re.compile(r"WAL usage:.*?,\s*(\d+)\s+bytes", re.I | re.S)
_TUPLES_RE = re.compile(r"tuples:\s*(\d+)\s+removed", re.I)
_DEAD_RE = re.compile(r"(\d+)\s+are dead but not yet removable", re.I)
_MANUAL_RE = re.compile(r"\b(vacuum|analyze|reindex)\b", re.I)


@dataclass(frozen=True)
class _Event:
    record: Any
    kind: str
    relation: str | None
    duration_s: float | None
    pages_removed: int | None
    relation_pages_after: int | None
    scanned_pages: int | None
    processed_pages: int | None
    processed_bytes: int | None
    buffer_bytes: int | None
    wal_bytes: int | None
    tuples_removed: int | None
    dead_not_removable: int | None
    inclusion_reason: str
    impact_score: float


def collect(context: PythonSourceContext) -> PythonSourceResult:
    window, early = resolve_english_window(context)
    if early is not None:
        return PythonSourceResult(**early)
    block_size = _block_size(context)
    matched = 0
    below_threshold = 0
    events: list[_Event] = []
    for record in window.records:
        event, was_maintenance = _parse_event(record, block_size)
        if not was_maintenance:
            continue
        matched += record.repeat_count
        if event is None:
            below_threshold += record.repeat_count
        else:
            events.append(event)
    events.sort(key=lambda event: (event.impact_score, event.record.last_time), reverse=True)
    omitted = max(0, len(events) - ROW_LIMIT)
    rows: list[dict[str, Any]] = [
        {
            "log_time": fmt_time(event.record.log_time),
            "kind": event.kind,
            "relation": event.relation,
            "inclusion_reason": event.inclusion_reason,
            "impact_score": round(event.impact_score, 3),
            "duration_s": event.duration_s,
            "pages_removed": event.pages_removed,
            "relation_pages_after": event.relation_pages_after,
            "scanned_pages": event.scanned_pages,
            "processed_pages": event.processed_pages,
            "processed_bytes": event.processed_bytes,
            "buffer_bytes": event.buffer_bytes,
            "wal_bytes": event.wal_bytes,
            "tuples_removed": event.tuples_removed,
            "dead_not_removable": event.dead_not_removable,
            "severity": event.record.severity,
            "sql_state": event.record.sql_state,
            "database_name": event.record.database_name,
            "application_name": event.record.application_name,
            "query_id": event.record.query_id,
            "occurrences": event.record.repeat_count,
            "message": event.record.message,
            "count_complete": event.record.count_complete,
        }
        for event in events[:ROW_LIMIT]
    ]
    thresholds = {
        "duration_seconds": DURATION_SECONDS_THRESHOLD,
        "processed_bytes": PAGE_BYTES_THRESHOLD,
        "buffer_read_plus_dirtied_bytes": BUFFER_BYTES_THRESHOLD,
        "wal_bytes": WAL_BYTES_THRESHOLD,
        "errors_cancellations_lock_waits_wraparound": "always",
    }
    result = table_result(rows)
    result.update(
        {
            "thresholds": thresholds,
            "block_size_bytes": block_size,
            "matched_event_count": matched,
            "below_threshold_event_count": below_threshold,
            "qualifying_series_count": len(events),
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
    description = f"{len(events)} heavy/error maintenance series qualified; {len(rows)} are shown. {below_threshold} successful low-impact event(s) were intentionally filtered by documented thresholds."
    if omitted:
        description += f" {omitted} lower-impact qualifying series were omitted by the fixed {ROW_LIMIT}-row limit."
    if note:
        description += f" {note}"
    has_failure = any(
        event.inclusion_reason in {"error_or_cancellation", "lock_wait", "wraparound_emergency"}
        for event in events
    )
    severity = "unknown" if note else ("high" if has_failure else "medium")
    return PythonSourceResult(
        collection_status="ok",
        result=result,
        severity_level=severity,
        issues={
            "summary": {
                "severity": severity,
                "status": "review",
                "title": "Heavy or failed maintenance events need review",
                "description": description,
                "recommendation": "Review the highest impact_score first; correlate duration, scanned/buffer/WAL bytes, tuple cleanup, blockers, wraparound risk, and maintenance scheduling.",
            },
            "items": [],
        },
    )


def _parse_event(record: Any, block_size: int) -> tuple[_Event | None, bool]:
    message = record.message_full or record.message
    head = _AUTO_HEAD_RE.search(message)
    is_autovacuum = (
        record.backend_type == "autovacuum worker" or message == "canceling autovacuum task"
    )
    if head is None and is_autovacuum:
        head = _AUTO_HEAD_RE.search(record.context or "")
    command = (record.command_tag or "").upper()
    is_manual = command in {"VACUUM", "ANALYZE", "REINDEX"}
    message_maintenance = _MANUAL_RE.search(message) is not None
    if head is None and not is_manual and not message_maintenance and not is_autovacuum:
        return None, False
    kind = (
        f"auto{head.group('kind').lower()}"
        if head
        else ("autovacuum" if is_autovacuum else (command.lower() or "maintenance"))
    )
    relation = head.group("relation") if head else None
    duration_s = _float_match(_ELAPSED_RE, message)
    if duration_s is None and is_manual:
        duration_ms = _float_match(_DURATION_MS_RE, message)
        duration_s = duration_ms / 1000.0 if duration_ms is not None else None
    lock_wait_ms = _float_match(_LOCK_WAIT_MS_RE, message) if is_manual else None
    if duration_s is None and lock_wait_ms is not None:
        duration_s = lock_wait_ms / 1000.0
    pages = _PAGES_RE.search(message)
    pages_removed = int(pages.group("removed")) if pages else None
    relation_pages_after = int(pages.group("remain")) if pages else None
    scanned_pages = int(pages.group("scanned")) if pages and pages.group("scanned") else None
    # PostgreSQL 10-14 do not report the number of scanned pages.  Their
    # ``remain`` value is the post-vacuum relation size, not work performed;
    # treating it as traffic would flag large, mostly-skipped relations.
    processed_pages = scanned_pages
    processed_bytes = processed_pages * block_size if processed_pages is not None else None
    buffers = _BUFFER_RE.search(message)
    buffer_blocks = (int(buffers.group(2)) + int(buffers.group(3))) if buffers else None
    buffer_bytes = buffer_blocks * block_size if buffer_blocks is not None else None
    wal = _WAL_RE.search(message)
    wal_bytes = int(wal.group(1)) if wal else None
    tuples = _TUPLES_RE.search(message)
    tuples_removed = int(tuples.group(1)) if tuples else None
    dead = _DEAD_RE.search(message)
    dead_not_removable = int(dead.group(1)) if dead else None
    lowered = message.lower()
    is_failure = record.severity in {"ERROR", "FATAL", "PANIC"} or record.sql_state in {
        "57014",
        "55P03",
    }
    wraparound = "wraparound" in lowered or "to prevent wraparound" in lowered
    scores = [
        (duration_s or 0.0) / DURATION_SECONDS_THRESHOLD,
        (processed_bytes or 0) / PAGE_BYTES_THRESHOLD,
        (buffer_bytes or 0) / BUFFER_BYTES_THRESHOLD,
        (wal_bytes or 0) / WAL_BYTES_THRESHOLD,
    ]
    impact_score = max(scores)
    if wraparound:
        reason, impact_score = "wraparound_emergency", max(impact_score, 2.0)
    elif is_failure:
        reason, impact_score = "error_or_cancellation", max(impact_score, 2.0)
    elif lock_wait_ms is not None:
        reason, impact_score = "lock_wait", max(impact_score, 2.0)
    elif impact_score >= 1.0:
        reason = "threshold_exceeded"
    else:
        return None, True
    return _Event(
        record,
        kind,
        relation,
        duration_s,
        pages_removed,
        relation_pages_after,
        scanned_pages,
        processed_pages,
        processed_bytes,
        buffer_bytes,
        wal_bytes,
        tuples_removed,
        dead_not_removable,
        reason,
        impact_score,
    ), True


def _float_match(pattern: re.Pattern[str], value: str) -> float | None:
    match = pattern.search(value)
    return float(match.group(1)) if match else None


def _block_size(context: Any) -> int:
    inventory = getattr(context.server_log, "inventory", None) or {}
    settings = inventory.get("settings") or {}
    try:
        value = int(settings.get("block_size") or 8192)
    except (TypeError, ValueError):
        value = 8192
    return value if 1024 <= value <= 1_048_576 else 8192
