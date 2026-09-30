from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
import heapq
import math
from typing import Any

from pg_diag.logscan.query_links import query_reference

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult
from pg_diag.logscan.event_refs import CHART_POINT_LIMIT, ChartReferencePool
from pg_diag.logscan.items_common import (
    coverage_note,
    empty_result_status,
    log_clock_offset,
    resolve_english_window,
)

BUCKET_SECONDS = 60.0
TOP_QUERIES_PER_BUCKET = 15

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
    window, early = resolve_english_window(context)
    if early is not None:
        return PythonSourceResult(**early)
    settings = (getattr(context, "source", None) or {}).get("settings", {})
    bucket_seconds = settings.get("bucket_seconds", BUCKET_SECONDS)
    if (isinstance(bucket_seconds, bool) or not isinstance(bucket_seconds, (int, float))
            or not math.isfinite(bucket_seconds) or bucket_seconds < 1):
        raise ValueError("settings.bucket_seconds must be a finite number >= 1")

    # The query catalog is shared by all items. Bound only this item's retained
    # executions; one SQL identity may have multiple timings and different plans.
    retained: dict[tuple[str | None, int], Any] = {}
    fastest: list[tuple[float, int, str | None]] = []
    format_counts: Counter[str] = Counter()
    duration_band_counts: Counter[str] = Counter()
    plan_count = parsed_plan_count = complete_plan_count = node_count = 0
    sequence = 0
    for record in window.records:
        plan = record.auto_explain_plan
        if plan is None:
            continue
        count = max(record.repeat_count, 1)
        plan_count += count
        format_counts[plan.plan_format] += count
        duration_band_counts[_duration_band(plan.duration_ms)] += count
        if plan.parsed:
            parsed_plan_count += count
            node_count += plan.node_count * count
        if plan.complete:
            complete_plan_count += count
        identity = query_reference(record.query or plan.query_text, record.query_id)
        # At most limit copies of one repeated event could survive. Real plan
        # events are not RLE-merged, so normally count == 1.
        for _ in range(min(count, CHART_POINT_LIMIT)):
            sequence += 1
            # Equal durations retain the earlier input event. The unique
            # sequence keeps heap comparisons away from records or SQL text.
            candidate = (plan.duration_ms, -sequence, identity)
            key = (identity, sequence)
            if len(fastest) < CHART_POINT_LIMIT:
                heapq.heappush(fastest, candidate)
            elif candidate[:2] > fastest[0][:2]:
                removed = heapq.heapreplace(fastest, candidate)
                del retained[(removed[2], -removed[1])]
            else:
                continue
            retained[key] = record

    # Intern plans only after eviction, slowest first. Evicted executions never
    # consume the final reference budget; the byte cap favors the slowest plans.
    ordered = [retained[(identity, -order)]
               for _duration, order, identity in sorted(fastest, reverse=True)]
    selected: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    bucket_sizes = Counter(_floor_time(record.log_time, bucket_seconds) for record in ordered)
    utc_offset_seconds, clock_diagnostics = log_clock_offset(context)
    refs = ChartReferencePool()
    for record in ordered:
        bucket = _floor_time(record.log_time, bucket_seconds)
        if len(selected[bucket]) >= TOP_QUERIES_PER_BUCKET:
            continue
        selected[bucket].append(_chart_point(
            bucket, record, utc_offset_seconds, len(selected[bucket]),
            min(bucket_sizes[bucket], TOP_QUERIES_PER_BUCKET), refs,
        ))
    displayed_plan_count = sum(len(points) for points in selected.values())
    evicted_plan_count = plan_count - len(ordered)
    bucket_omitted_plan_count = len(ordered) - displayed_plan_count
    omitted_plan_count = plan_count - displayed_plan_count
    rank_count = max((len(points) for points in selected.values()), default=0)

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
                "points": [selected[bucket][rank] for bucket in sorted(selected)
                           if rank < len(selected[bucket])],
            }
            # ECharts draws the first stacked series at the bottom. Declare
            # higher ranks first so durations descend top-to-bottom.
            for rank in range(rank_count - 1, -1, -1)
        ],
        "references": refs.as_dict(),
        "bucket_seconds": bucket_seconds,
        "top_queries_per_bucket": TOP_QUERIES_PER_BUCKET,
        "selection_policy": "slowest_executions",
        "max_displayed_queries_per_bucket": rank_count,
        "plan_count": plan_count,
        "displayed_plan_count": displayed_plan_count,
        "omitted_plan_count": omitted_plan_count,
        "evicted_plan_count": evicted_plan_count,
        "global_retained_plan_count": len(ordered),
        "bucket_omitted_plan_count": bucket_omitted_plan_count,
        "minimum_retained_duration_ms": fastest[0][0] if fastest else None,
        "candidate_point_count": plan_count,
        "point_limit": CHART_POINT_LIMIT,
        "display_point_count": displayed_plan_count,
        "reference_omitted_count": refs.omitted_total,
        "parsed_plan_count": parsed_plan_count,
        "complete_plan_count": complete_plan_count,
        "plan_node_count": node_count,
        "plan_format_counts": dict(sorted(format_counts.items())),
        "duration_band_counts": {
            label: duration_band_counts[label] for label, _lower, _upper, _color in _BANDS
        },
    }

    if not plan_count:
        status, severity, issues = empty_result_status(window)
        return PythonSourceResult(
            collection_status=status,
            result=result,
            issues=issues,
            severity_level=severity,
            diagnostics=clock_diagnostics,
        )

    note = coverage_note(window)
    unparsed = result["plan_count"] - parsed_plan_count
    incomplete = result["plan_count"] - complete_plan_count
    selection_summary = (
        f"{plan_count} auto_explain execution(s) collected; {len(ordered)} retained "
        f"by the global limit, {displayed_plan_count} displayed. "
        f"{evicted_plan_count} execution(s) evicted by duration priority under the "
        f"{CHART_POINT_LIMIT}-execution limit. From the retained executions, each "
        f"{bucket_seconds:g}-second bucket shows at most {TOP_QUERIES_PER_BUCKET} "
        f"slowest executions; {bucket_omitted_plan_count} additional execution(s) "
        "omitted by the per-bucket limit. Repeated SQL retains separate executions "
        "and plans. Equal-duration ties retain earlier input events."
    )
    severity = "ok"
    details = []
    if unparsed:
        details.append(f"{unparsed} plan(s) had an unrecognized or truncated body")
    if incomplete:
        details.append(f"{incomplete} plan record(s) exceeded the capture boundary")
    if note:
        details.append(note)
    if refs.omitted_total:
        details.append(f"{refs.omitted_total} query or plan reference(s) exceeded payload budgets")
    if details:
        severity = "unknown"
    issues = {
        "summary": {
            "severity": severity,
            "status": "review" if details or omitted_plan_count else "ok",
            "title": "Auto-explain chart has incomplete plan evidence" if details
            else "Slowest auto-explain executions across the collected window",
            "description": " ".join([selection_summary, *details]),
            "recommendation": (
                "Inspect the highest-duration executions and their plans. This chart is "
                "selected by duration, not execution frequency or total workload."
                + (" Review collection coverage and plan payload limits for missing evidence."
                   if details else "")
            ),
        },
        "items": [],
    }
    return PythonSourceResult(
        collection_status="ok",
        result=result,
        issues=issues,
        severity_level=severity,
        diagnostics=clock_diagnostics,
    )


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
    """Return a positional red-to-yellow color for one bucket's stack."""
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
    refs: ChartReferencePool,
) -> dict[str, Any]:
    plan = record.auto_explain_plan
    assert plan is not None
    point = {
        "t": _iso_timestamp(bucket, _record_offset(record, utc_offset_seconds)),
        "value": plan.duration_ms,
        "color": _stack_color(rank, bucket_size),
        "tooltip": {
            "log_time": _iso_timestamp(record.log_time, _record_offset(record, utc_offset_seconds)),
            "duration_ms": plan.duration_ms,
            "query_ref": query_reference(record.query or plan.query_text, record.query_id)
            if record.query or plan.query_text else None,
        },
    }
    if plan.viewer_plan:
        plan_ref = refs.add_plan(plan.plan_format, plan.viewer_plan)
    else:
        plan_ref = None
    if plan_ref:
        point["viewer"] = {
            "plan_ref": plan_ref,
            "read_only": True,
        }
    return point


def _record_offset(record: Any, window_offset: int) -> int:
    """The record's own UTC offset when the log clock is known (DST-aware)."""
    offset = getattr(record, "utc_offset_seconds", None)
    return window_offset if offset is None else int(offset)


def _iso_timestamp(value: datetime, utc_offset_seconds: int) -> str:
    sign = "+" if utc_offset_seconds >= 0 else "-"
    offset = abs(utc_offset_seconds)
    hours, remainder = divmod(offset, 3600)
    minutes = remainder // 60
    stamp = value.isoformat(timespec="milliseconds" if value.microsecond else "seconds")
    return f"{stamp}{sign}{hours:02d}:{minutes:02d}"
