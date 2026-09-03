from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
import math
from typing import Any

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult
from pg_diag.logscan.csvparse import parse_timestamp
from pg_diag.logscan.items_common import coverage_note, empty_result_status, resolve_window

BUCKET_SECONDS = 60.0
TOP_QUERIES_PER_BUCKET = 10

_BANDS = (
    ("< 100 ms", 0.0, 100.0, "#4ade80"),
    ("100 ms - 1 s", 100.0, 1_000.0, "#a3e635"),
    ("1 - 10 s", 1_000.0, 10_000.0, "#facc15"),
    ("10 - 60 s", 10_000.0, 60_000.0, "#fb923c"),
    (">= 60 s", 60_000.0, None, "#f87171"),
)

_STACK_TOP_COLOR = (239, 68, 68)  # red-500
_STACK_BOTTOM_COLOR = (250, 204, 21)  # yellow-400


def collect(context: PythonSourceContext) -> PythonSourceResult:
    window, early = resolve_window(context)
    if early is not None:
        return PythonSourceResult(**early)

    records = [record for record in window.records if record.auto_explain_plan is not None]
    bucket_start, bucket_end = _bucket_bounds(context, records, BUCKET_SECONDS)
    buckets = _buckets(bucket_start, bucket_end, BUCKET_SECONDS)
    records_by_bucket = defaultdict(list)
    format_counts: Counter[str] = Counter()
    duration_band_counts: Counter[str] = Counter()
    parsed_plan_count = 0
    complete_plan_count = 0
    node_count = 0

    for record in records:
        plan = record.auto_explain_plan
        assert plan is not None
        bucket = _floor_time(record.log_time, BUCKET_SECONDS)
        label = _duration_band(plan.duration_ms)
        records_by_bucket[bucket].extend(
            [record] * min(max(record.repeat_count, 1), TOP_QUERIES_PER_BUCKET)
        )
        format_counts[plan.plan_format] += record.repeat_count
        duration_band_counts[label] += record.repeat_count
        if plan.parsed:
            parsed_plan_count += record.repeat_count
            node_count += plan.node_count * record.repeat_count
        if plan.complete:
            complete_plan_count += record.repeat_count

    top_by_bucket = {
        bucket: sorted(
            bucket_records,
            key=lambda record: (
                -record.auto_explain_plan.duration_ms,
                record.log_time,
                record.process_id or -1,
            ),
        )[:TOP_QUERIES_PER_BUCKET]
        for bucket, bucket_records in records_by_bucket.items()
    }
    utc_offset_seconds = _utc_offset_seconds(context)
    displayed_plan_count = sum(len(bucket_records) for bucket_records in top_by_bucket.values())

    result = {
        "kind": "chart",
        "chart": {
            "kind": "stacked_column",
            "x_type": "datetime",
            "quantity": "milliseconds",
            "unit": "milliseconds",
            "series_order": "configured",
            "show_legend": False,
            "tooltip_kind": "query_event",
        },
        "series": [
            {
                "name": f"Rank {rank + 1}",
                "label": f"Rank {rank + 1}",
                "value_kind": "decimal",
                "semantic_role": "duration",
                "quality": "derived",
                "encoding": "json_number",
                "nullable": False,
                "quantity": "milliseconds",
                "unit": "milliseconds",
                "points": [
                    _chart_point(
                        bucket,
                        (top_by_bucket.get(bucket) or [])[rank]
                        if rank < len(top_by_bucket.get(bucket) or [])
                        else None,
                        utc_offset_seconds,
                        rank,
                        len(top_by_bucket.get(bucket) or []),
                    )
                    for bucket in buckets
                ],
            }
            # ECharts draws the first stacked series at the bottom. Declare
            # Rank 10 first and Rank 1 last so durations descend top-to-bottom.
            for rank in range(TOP_QUERIES_PER_BUCKET - 1, -1, -1)
        ],
        "bucket_seconds": BUCKET_SECONDS,
        "top_queries_per_bucket": TOP_QUERIES_PER_BUCKET,
        "plan_count": sum(record.repeat_count for record in records),
        "displayed_plan_count": displayed_plan_count,
        "omitted_plan_count": max(
            0,
            sum(record.repeat_count for record in records) - displayed_plan_count,
        ),
        "parsed_plan_count": parsed_plan_count,
        "complete_plan_count": complete_plan_count,
        "plan_node_count": node_count,
        "plan_format_counts": dict(sorted(format_counts.items())),
        "duration_band_counts": {
            label: duration_band_counts[label] for label, _lower, _upper, _color in _BANDS
        },
    }

    if not records:
        status, severity, issues = empty_result_status(window)
        return PythonSourceResult(
            collection_status=status,
            result=result,
            issues=issues,
            severity_level=severity,
        )

    note = coverage_note(window)
    unparsed = result["plan_count"] - parsed_plan_count
    incomplete = result["plan_count"] - complete_plan_count
    issues: dict[str, Any] = {}
    severity = "ok"
    if note or unparsed or incomplete:
        severity = "unknown"
        details = []
        if unparsed:
            details.append(f"{unparsed} plan(s) had an unrecognized or truncated body")
        if incomplete:
            details.append(f"{incomplete} plan record(s) exceeded the capture boundary")
        if note:
            details.append(note)
        issues = {
            "summary": {
                "severity": "unknown",
                "status": "review",
                "title": "Auto-explain chart has incomplete plan evidence",
                "description": " ".join(details),
                "recommendation": (
                    "Reduce the log window or auto_explain volume when collection limits were "
                    "hit; prefer auto_explain.log_format=json for machine-readable plans."
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


def _bucket_bounds(
    context, records, bucket_seconds: float
) -> tuple[datetime | None, datetime | None]:
    inventory = getattr(context.server_log, "inventory", None) or {}
    start = parse_timestamp(str(inventory.get("window_from") or ""))
    end = parse_timestamp(str(inventory.get("collected_to") or ""))
    if start is None and records:
        start = min(record.log_time for record in records)
    if end is None and records:
        end = max(record.log_time for record in records)
    if start is None or end is None:
        return None, None
    return _floor_time(start, bucket_seconds), _floor_time(end, bucket_seconds)


def _buckets(start: datetime | None, end: datetime | None, seconds: float) -> list[datetime]:
    if start is None or end is None or end < start:
        return []
    count = int(math.floor((end - start).total_seconds() / seconds)) + 1
    return [start + timedelta(seconds=index * seconds) for index in range(count)]


def _floor_time(value: datetime, seconds: float) -> datetime:
    epoch = datetime(1970, 1, 1)
    elapsed = (value - epoch).total_seconds()
    return epoch + timedelta(seconds=math.floor(elapsed / seconds) * seconds)


def _duration_band(duration_ms: float) -> str:
    for label, lower, upper, _color in _BANDS:
        if duration_ms >= lower and (upper is None or duration_ms < upper):
            return label
    return _BANDS[-1][0]


def _stack_color(rank: int, bucket_size: int) -> str:
    """Return a positional red-to-yellow color for one minute's stack."""
    if bucket_size <= 1:
        return _hex_color(_STACK_TOP_COLOR)
    position = min(max(rank, 0), bucket_size - 1) / (bucket_size - 1)
    rgb = tuple(
        round(top + (bottom - top) * position)
        for top, bottom in zip(_STACK_TOP_COLOR, _STACK_BOTTOM_COLOR, strict=True)
    )
    return _hex_color(rgb)


def _hex_color(rgb: tuple[int, ...]) -> str:
    return "#" + "".join(f"{channel:02x}" for channel in rgb)


def _chart_point(
    bucket: datetime,
    record,
    utc_offset_seconds: int,
    rank: int,
    bucket_size: int,
) -> dict[str, Any]:
    point = {
        "t": _iso_timestamp(bucket, utc_offset_seconds),
        "value": 0,
    }
    if record is None:
        return point
    plan = record.auto_explain_plan
    assert plan is not None
    point.update(
        {
            "value": plan.duration_ms,
            "color": _stack_color(rank, bucket_size),
            "tooltip": {
                "log_time": _iso_timestamp(record.log_time, utc_offset_seconds),
                "duration_ms": plan.duration_ms,
                "query_sample": plan.query_sample,
            },
        }
    )
    if plan.viewer_plan:
        point["viewer"] = {
            "plan_text": plan.viewer_plan,
            "plan_format": plan.plan_format,
            "read_only": True,
        }
    return point


def _utc_offset_seconds(context) -> int:
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
