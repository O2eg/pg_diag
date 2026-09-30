from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import blake2b
import re
from typing import Any

from pg_diag.logscan.query_links import group_query_columns, remember_query

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result
from pg_diag.logscan.items_common import (
    coverage_note,
    empty_result_status,
    fmt_time,
    resolve_english_window,
)

ROW_LIMIT = 100
_DURATION_RE = re.compile(
    r"^duration:\s*(?P<duration>\d+(?:\.\d+)?)\s*ms"
    r"(?:\s+(?P<stage>statement|(?:execute|parse|bind)\s+[^:]+):\s*(?P<query>.*))?\s*$",
    re.DOTALL,
)
_TEMP_RE = re.compile(r'^temporary file:\s+path\s+"[^"]+",\s+size\s+(?P<size>\d+)')


@dataclass
class _Aggregate:
    event_type: str
    first_time: Any
    last_time: Any
    occurrences: int = 0
    max_duration_ms: float | None = None
    total_duration_ms: float = 0.0
    max_temp_bytes: int | None = None
    total_temp_bytes: int = 0
    database_name: str | None = None
    user_name: str | None = None
    application_name: str | None = None
    query_id: int | None = None
    message_sample: str | None = None
    count_complete: bool = True
    database_partial: bool = False
    collector_generated: bool = False
    queries: dict = field(default_factory=dict)


def collect(context: PythonSourceContext) -> PythonSourceResult:
    window, early = resolve_english_window(context)
    if early is not None:
        return PythonSourceResult(**early)
    aggregates: dict[tuple[Any, ...], _Aggregate] = {}
    raw_event_count = 0
    for record in window.records:
        message = record.message_full or record.message
        duration = _DURATION_RE.match(message)
        temporary = _TEMP_RE.match(message)
        if duration is None and temporary is None:
            continue
        event_type = "temporary_file"
        if duration is not None:
            stage = (duration.group("stage") or "duration_only").split()[0]
            event_type = {
                "statement": "slow_statement", "execute": "slow_statement",
                "parse": "parse_duration", "bind": "bind_duration",
                "duration_only": "duration_only",
            }[stage]
        query = record.query or (duration.group("query") if duration is not None else None)
        query = query.strip() if query else None
        identity = (
            str(record.query_id)
            if record.query_id not in (None, 0)
            else _digest(query or record.fingerprint)
        )
        # Known databases stay part of the identity: the same query from two databases is
        # two groups. Records without a database (temporary files logged while a backend
        # exits) are attached after the scan, only when exactly one database group matches.
        key = (event_type, identity, record.application_name, record.database_name)
        aggregate = aggregates.get(key)
        if aggregate is None:
            aggregate = _Aggregate(
                event_type=event_type,
                first_time=record.log_time,
                last_time=record.last_time,
                database_name=record.database_name,
                user_name=record.user_name,
                application_name=record.application_name,
                query_id=record.query_id or None,
                message_sample=record.message[:500],
                collector_generated=_is_collector_generated(query, record.application_name),
            )
            aggregates[key] = aggregate
        remember_query(aggregate.queries, query, record.query_id)
        if record.database_name is None:
            aggregate.database_partial = True
        if aggregate.user_name is None:
            aggregate.user_name = record.user_name
        count = max(record.repeat_count, 1)
        raw_event_count += count
        aggregate.first_time = min(aggregate.first_time, record.log_time)
        aggregate.last_time = max(aggregate.last_time, record.last_time)
        aggregate.occurrences += count
        aggregate.count_complete = aggregate.count_complete and record.count_complete
        if duration is not None:
            duration_ms = float(duration.group("duration"))
            aggregate.max_duration_ms = max(aggregate.max_duration_ms or 0.0, duration_ms)
            aggregate.total_duration_ms += duration_ms * count
        if temporary is not None:
            temp_bytes = int(temporary.group("size"))
            aggregate.max_temp_bytes = max(aggregate.max_temp_bytes or 0, temp_bytes)
            aggregate.total_temp_bytes += temp_bytes * count

    _attach_databaseless_groups(aggregates)
    ranked = sorted(
        aggregates.values(),
        key=lambda row: (
            not row.collector_generated,
            row.total_temp_bytes,
            row.max_duration_ms or 0.0,
            row.total_duration_ms,
            row.occurrences,
        ),
        reverse=True,
    )
    omitted = max(0, len(ranked) - ROW_LIMIT)
    rows: list[dict[str, Any]] = [
        {
            "event_type": row.event_type,
            "occurrences": row.occurrences,
            "first_time": fmt_time(row.first_time),
            "last_time": fmt_time(row.last_time),
            "max_duration_ms": row.max_duration_ms,
            "total_duration_ms": round(row.total_duration_ms, 3)
            if row.max_duration_ms is not None
            else None,
            "max_temp_bytes": row.max_temp_bytes,
            "total_temp_bytes": row.total_temp_bytes if row.max_temp_bytes is not None else None,
            "database_name": row.database_name,
            "user_name": row.user_name,
            "application_name": row.application_name,
            **group_query_columns({"queries": row.queries}),
            "message_sample": row.message_sample,
            "database_partial": row.database_partial,
            "collector_generated": row.collector_generated,
            "count_complete": row.count_complete,
        }
        for row in ranked[:ROW_LIMIT]
    ]
    collector_groups = [row for row in ranked if row.collector_generated]
    collector_event_count = sum(row.occurrences for row in collector_groups)
    result = table_result(rows)
    result.update(
        {
            "raw_event_count": raw_event_count,
            "event_counts_by_type": {
                kind: sum(row.occurrences for row in ranked if row.event_type == kind)
                for kind in sorted({row.event_type for row in ranked})
            },
            "aggregate_count": len(ranked),
            "omitted_aggregate_count": omitted,
            "collector_generated_group_count": len(collector_groups),
            "collector_generated_event_count": collector_event_count,
            "row_limit": ROW_LIMIT,
        }
    )
    if not rows:
        status, severity, issues = empty_result_status(window)
        return PythonSourceResult(
            collection_status=status, result=result, issues=issues, severity_level=severity
        )
    note = coverage_note(window)
    workload_groups = len(ranked) - len(collector_groups)
    description = (
        f"{raw_event_count - collector_event_count} resource event(s) form {workload_groups} "
        f"query/resource groups; {len(rows)} rows are shown."
    )
    description += (
        " Parse, bind, and duration-only timings are separate event types, not additional "
        "statement executions; do not sum stages to infer end-to-end query latency."
    )
    if collector_groups:
        description += (
            f" {collector_event_count} event(s) in {len(collector_groups)} group(s) were generated by "
            "pg_diag itself (collector_generated=true) and are listed last."
        )
    if not workload_groups:
        severity_override = "ok"
    else:
        severity_override = None
    if omitted:
        description += (
            f" {omitted} lower-impact groups were omitted by the fixed {ROW_LIMIT}-row limit."
        )
    if note:
        description += f" {note}"
    severity = "unknown" if note else (severity_override or "medium")
    return PythonSourceResult(
        collection_status="ok",
        result=result,
        severity_level=severity,
        issues={
            "summary": {
                "severity": severity,
                "status": "review" if severity != "ok" else "ok",
                "title": "Queries consumed notable time or temporary storage",
                "description": description,
                "recommendation": "Prioritize groups by total/max temporary bytes and duration; open SQL through Query ID and correlate database and application with plans and work_mem settings.",
            },
            "items": [],
        },
    )


def _attach_databaseless_groups(aggregates: dict[tuple[Any, ...], _Aggregate]) -> None:
    """Merge a database-less group into the single database group with the same identity.

    With several candidate databases the records stay a separate group with
    ``database_name`` empty and ``database_partial`` set, so the ambiguity remains visible
    instead of being attributed to whichever database was logged first.
    """
    for key in [key for key in aggregates if key[3] is None]:
        candidates = [
            other for other in aggregates if other[:3] == key[:3] and other[3] is not None
        ]
        if len(candidates) != 1:
            continue
        target = aggregates[candidates[0]]
        source = aggregates.pop(key)
        target.first_time = min(target.first_time, source.first_time)
        target.last_time = max(target.last_time, source.last_time)
        target.occurrences += source.occurrences
        for identity, reference in source.queries.items():
            target.queries[identity] = target.queries.get(identity) or reference
        target.total_duration_ms += source.total_duration_ms
        target.total_temp_bytes += source.total_temp_bytes
        if source.max_duration_ms is not None:
            target.max_duration_ms = max(target.max_duration_ms or 0.0, source.max_duration_ms)
        if source.max_temp_bytes is not None:
            target.max_temp_bytes = max(target.max_temp_bytes or 0, source.max_temp_bytes)
        target.count_complete = target.count_complete and source.count_complete
        target.database_partial = True
        if target.user_name is None:
            target.user_name = source.user_name


def _digest(value: str) -> str:
    return blake2b(value.encode("utf-8", "replace"), digest_size=12).hexdigest()


_COLLECTOR_QUERY_MARKER = "/* pg_diag:"
_COLLECTOR_APPLICATION_NAME = "pg_diag"


def _is_collector_generated(query: str | None, application_name: str | None) -> bool:
    """True for records produced by pg_diag's own sampling queries."""
    if application_name and application_name.strip().lower() == _COLLECTOR_APPLICATION_NAME:
        return True
    return bool(query) and query.lstrip().startswith(_COLLECTOR_QUERY_MARKER)
