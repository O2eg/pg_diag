from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import datetime
from typing import Any

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult
from pg_diag.logscan.event_refs import CHART_POINT_LIMIT, ChartReferencePool
from pg_diag.logscan.items_common import coverage_note, empty_result_status, resolve_window

TOP_EVENTS_PER_MINUTE = 10


def collect(context: PythonSourceContext) -> PythonSourceResult:
    window, early = resolve_window(context)
    if early is not None:
        return PythonSourceResult(**early)

    groups_by_minute: dict[datetime, dict[tuple[Any, ...], tuple[Any, str]]] = defaultdict(dict)
    matched = 0
    for record in window.records:
        kind = _event_kind(record)
        if kind is None:
            continue
        matched += record.repeat_count
        minute = _floor_minute(record.log_time)
        key = (
            kind,
            record.sql_state,
            record.database_name,
            record.user_name,
            record.application_name,
            record.query_id or None,
            record.message,
            record.query,
        )
        previous = groups_by_minute[minute].get(key)
        if previous is not None:
            head = previous[0]
            record = replace(
                head,
                log_time=min(head.log_time, record.log_time),
                last_time=max(head.last_time, record.last_time),
                repeat_count=head.repeat_count + record.repeat_count,
                count_complete=head.count_complete and record.count_complete,
            )
        groups_by_minute[minute][key] = (record, kind)
    events_by_minute = {
        minute: sorted(
            groups.values(),
            key=lambda item: (item[0].repeat_count, item[0].log_time),
            reverse=True,
        )
        for minute, groups in groups_by_minute.items()
    }

    selected: list[tuple[int, datetime, Any, str]] = []
    # Fair global cap: retain rank 1 from every active minute before rank 2.
    for rank in range(TOP_EVENTS_PER_MINUTE):
        for minute in sorted(events_by_minute):
            events = events_by_minute[minute]
            if rank < len(events) and len(selected) < CHART_POINT_LIMIT:
                record, kind = events[rank]
                selected.append((rank, minute, record, kind))

    refs = ChartReferencePool()
    points_by_rank: dict[int, list[dict[str, Any]]] = defaultdict(list)
    utc_offset = _utc_offset_seconds(context)
    for rank, minute, record, kind in selected:
        message_ref = refs.add_message(record.message)
        query_ref = refs.add_query(record.query)
        points_by_rank[rank].append(
            {
                "t": _iso_timestamp(minute, utc_offset),
                "value": record.repeat_count,
                "tooltip": {
                    "log_time": _iso_timestamp(record.log_time, utc_offset),
                    "last_log_time": _iso_timestamp(record.last_time, utc_offset),
                    "event_type": kind,
                    "sql_state": record.sql_state,
                    "occurrences": record.repeat_count,
                    "database_name": record.database_name,
                    "user_name": record.user_name,
                    "application_name": record.application_name,
                    "message_ref": message_ref,
                    "query_ref": query_ref,
                },
            }
        )

    displayed = len(selected)
    candidate_points = sum(len(events) for events in events_by_minute.values())
    omitted = max(0, candidate_points - displayed)
    displayed_events = sum(record.repeat_count for _, _, record, _ in selected)
    omitted_events = max(0, matched - displayed_events)
    result = {
        "kind": "chart",
        "chart": {
            "kind": "stacked_column",
            "x_type": "datetime",
            "quantity": "events",
            "unit": "count",
            "series_order": "configured",
            "show_legend": False,
            "tooltip_kind": "log_event",
        },
        "series": [
            {
                "name": f"Rank {rank + 1}",
                "label": f"Rank {rank + 1}",
                "value_kind": "integer",
                "semantic_role": "counter_delta",
                "quality": "derived",
                "encoding": "json_number",
                "nullable": False,
                "quantity": "events",
                "unit": "count",
                "points": points_by_rank.get(rank, []),
            }
            for rank in range(TOP_EVENTS_PER_MINUTE - 1, -1, -1)
        ],
        "references": refs.as_dict(),
        "event_count": matched,
        "displayed_event_count": displayed_events,
        "omitted_event_count": omitted_events,
        "candidate_point_count": candidate_points,
        "displayed_point_count": displayed,
        "omitted_point_count": omitted,
        "point_limit": CHART_POINT_LIMIT,
        "top_events_per_minute": TOP_EVENTS_PER_MINUTE,
        "reference_omitted_count": refs.omitted_total,
        "message_pattern_coverage": (
            "full" if window.coverage.locale_supported else "structured_sqlstate_only"
        ),
    }
    if not selected:
        if not window.coverage.locale_supported:
            return PythonSourceResult(
                collection_status="ok",
                result=result,
                severity_level="unknown",
                issues={
                    "summary": {
                        "severity": "unknown",
                        "status": "review",
                        "title": "No SQLSTATE termination found, but subtype coverage is partial",
                        "description": (
                            "lc_messages is not English. SQLSTATE 57014, 55P03, and 57P01 were "
                            "checked, but message-only recovery conflicts could not be classified."
                        ),
                        "recommendation": (
                            "Review localized serialization/cancellation errors when recovery "
                            "conflicts are relevant."
                        ),
                    },
                    "items": [],
                },
            )
        status, severity, issues = empty_result_status(window)
        return PythonSourceResult(
            collection_status=status, result=result, issues=issues, severity_level=severity
        )
    note = coverage_note(window)
    locale_note = None
    if not window.coverage.locale_supported:
        locale_note = (
            "lc_messages is not English; SQLSTATE events are included, but cancellation "
            "subtypes and message-only recovery conflicts have partial classification."
        )
    incomplete = bool(note or omitted or refs.omitted_total or locale_note)
    description = (
        f"{matched} query termination event(s) form {candidate_points} minute/event groups; "
        f"{displayed} groups containing {displayed_events} events are shown."
    )
    if omitted:
        description += (
            f" {omitted} groups containing {omitted_events} events were omitted by the "
            f"top-{TOP_EVENTS_PER_MINUTE}-per-minute or global {CHART_POINT_LIMIT}-point limit."
        )
    if refs.omitted_total:
        description += (
            f" {refs.omitted_total} reference payloads were omitted by reference budgets."
        )
    if note:
        description += f" {note}"
    if locale_note:
        description += f" {locale_note}"
    severity = "unknown" if incomplete else "medium"
    return PythonSourceResult(
        collection_status="ok",
        result=result,
        severity_level=severity,
        issues={
            "summary": {
                "severity": severity,
                "status": "review",
                "title": "Queries were terminated",
                "description": description,
                "recommendation": "Correlate timeout, cancellation, recovery-conflict, shutdown, and NOWAIT points with workload latency, locks, failover, and application behavior.",
            },
            "items": [],
        },
    )


def _event_kind(record: Any) -> str | None:
    message = record.message.lower()
    if record.sql_state == "57P01":
        return "administrative_shutdown"
    if record.sql_state == "55P03":
        return "nowait_or_lock_not_available"
    if "conflict with recovery" in message:
        return "recovery_conflict"
    if record.sql_state != "57014":
        return None
    if "statement timeout" in message:
        return "statement_timeout"
    if "lock timeout" in message:
        return "lock_timeout"
    if "user request" in message:
        return "user_cancel"
    return "query_canceled"


def _floor_minute(value: datetime) -> datetime:
    return value.replace(second=0, microsecond=0)


def _utc_offset_seconds(context: Any) -> int:
    inventory = getattr(context.server_log, "inventory", None) or {}
    settings = inventory.get("settings") or {}
    try:
        offset = int(settings.get("log_utc_offset_seconds") or 0)
    except (TypeError, ValueError):
        return 0
    return max(-86_399, min(86_399, offset))


def _iso_timestamp(value: datetime, utc_offset_seconds: int) -> str:
    sign = "+" if utc_offset_seconds >= 0 else "-"
    offset = abs(utc_offset_seconds)
    hours, remainder = divmod(offset, 3600)
    minutes = remainder // 60
    stamp = value.isoformat(timespec="milliseconds" if value.microsecond else "seconds")
    return f"{stamp}{sign}{hours:02d}:{minutes:02d}"
