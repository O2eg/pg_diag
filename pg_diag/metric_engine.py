"""Build chart payloads from repeated SQL and OS metric samples."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pg_diag.artifact import item_from_plan
from pg_diag.contracts import (
    INTERVAL_COUNTER_DECREASE,
    INTERVAL_EPOCH_CHANGED,
    INTERVAL_INVALID_INTERVAL,
    INTERVAL_INVALID_VALUE,
    INTERVAL_MISSING_END,
    INTERVAL_MISSING_START,
    INTERVAL_NO_ACTIVITY,
    INTERVAL_OK,
    INTERVAL_STATUS_ORDER,
    interval_coverage_totals,
)
from pg_diag.planner import PlannedItem


SNAPSHOT_TIME_COLUMN = "snapshot_time"
SEVERITY_LEVEL_RANK = {"ok": 0, "unknown": 1, "medium": 2, "high": 3}


@dataclass(frozen=True)
class IntervalValue:
    value: float | None
    status: str


def build_metric_item(
    planned: PlannedItem,
    metric: dict[str, Any],
    db_snapshots: list[dict[str, Any]],
    os_samples: dict[str, list[dict[str, Any]]],
    source_item_by_query: dict[str, str],
    source_metadata_by_item: dict[str, dict[str, Any]],
    source_diagnostics: list[dict[str, Any]] | None = None,
    collection_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_query = metric.get("source_query")
    source_sampler = metric.get("source_sampler")
    source_text: str | None = None
    source_language: str | None = None
    metric_diagnostics: list[dict[str, Any]] = []
    source_failure_status: str | None = None
    source_failure_reason: str | None = None
    if source_query:
        source_item_id = source_item_by_query.get(source_query)
        if not source_item_id:
            return item_from_plan(
                planned,
                collection_status="error",
                reason=f"source query {source_query} was not collected",
                result=_empty_metric_result(metric),
                diagnostics=[
                    {
                        "level": "error",
                        "code": "metric_source_missing",
                        "message": f"Source query {source_query} is absent from collected items",
                    }
                ],
            )
        source_metadata = source_metadata_by_item.get(source_item_id, {})
        semantic_columns = source_metadata.get("semantic_columns") or {}
        source_columns = source_metadata.get("_result_columns") or []
        source_text = source_metadata.get("source_text")
        source_language = source_metadata.get("source_language") or "sql"
        source_items = [
            snapshot.get("items", {}).get(source_item_id)
            for snapshot in db_snapshots
            if snapshot.get("items", {}).get(source_item_id) is not None
        ]
        if not source_items:
            declared_status = source_metadata.get("_collection_status")
            status = (
                declared_status
                if declared_status in {"error", "unsupported", "skipped"}
                else "error"
            )
            reason = source_metadata.get("_reason") or (
                f"source query {source_query} produced no samples"
            )
            return item_from_plan(
                planned,
                collection_status=status,
                reason=str(reason),
                result=_empty_metric_result(metric),
                diagnostics=[
                    {
                        "level": "error" if status == "error" else "warning",
                        "code": "metric_source_status",
                        "message": (
                            f"Source query {source_query} produced no sample items; "
                            f"source status is {status}"
                        ),
                    }
                ],
                source_text=(
                    _metric_source_text(metric, source_text, source_language)
                    if source_text else None
                ),
                source_language=source_language,
            )
        source_failure_status, source_failure_reason, metric_diagnostics = _source_health(source_items)
        if source_failure_status and not _has_successful_source_item(source_items):
            return item_from_plan(
                planned,
                collection_status=source_failure_status,
                reason=source_failure_reason,
                result=_empty_metric_result(metric),
                diagnostics=metric_diagnostics,
                source_text=(
                    _metric_source_text(metric, source_text, source_language)
                    if source_text else None
                ),
                source_language=source_language,
            )
        samples = [
            {
                "timestamp": snapshot["timestamp"],
                "rows": _rows_from_item(
                    snapshot.get("items", {}).get(source_item_id),
                    source_columns,
                ),
            }
            for snapshot in db_snapshots
            if snapshot.get("items", {}).get(source_item_id) is not None
        ]
    elif source_sampler:
        samples = os_samples.get(source_sampler, [])
        semantic_columns = {}
        source_text = _sampler_source_text(source_sampler)
        source_language = "bash"
        metric_diagnostics = list(source_diagnostics or [])
        if not samples and metric_diagnostics:
            return item_from_plan(
                planned,
                collection_status=_sampler_failure_status(metric_diagnostics),
                reason=str(metric_diagnostics[0].get("message") or "sampler unavailable"),
                result=_empty_metric_result(metric),
                diagnostics=metric_diagnostics,
                source_text=_metric_source_text(metric, source_text, source_language),
                source_language=source_language,
            )
    else:
        return item_from_plan(
            planned,
            collection_status="empty",
            reason="metric has no source",
            result=_empty_metric_result(metric),
        )

    source_text = _metric_source_text(metric, source_text, source_language) if source_text else None

    if metric.get("result") == "table" or metric.get("table"):
        table = build_table_result(metric, samples, semantic_columns, collection_context)
        severity_level, issues = evaluate_metric_table_findings(
            table,
            metric.get("evaluation") or {},
        )
        coverage_reason, coverage_diagnostic = _interval_coverage_feedback(table)
        if coverage_diagnostic:
            metric_diagnostics.append(coverage_diagnostic)
        status = "ok" if table.get("rows") else "empty"
        if status == "empty" and source_failure_status == "error":
            status = "error"
        return item_from_plan(
            planned,
            collection_status=status,
            reason=source_failure_reason if status == "error" else coverage_reason,
            severity_level=severity_level,
            issues=issues,
            result=table,
            diagnostics=metric_diagnostics,
            source_text=source_text,
            source_language=source_language,
        )

    chart = build_chart_result(metric, samples, semantic_columns)
    coverage_reason, coverage_diagnostic = _interval_coverage_feedback(chart)
    if coverage_diagnostic:
        metric_diagnostics.append(coverage_diagnostic)
    status = "ok" if _chart_has_points(chart) else "empty"
    if status == "empty" and source_failure_status == "error":
        status = "error"
    return item_from_plan(
        planned,
        collection_status=status,
        reason=source_failure_reason if status == "error" else coverage_reason,
        result=chart,
        diagnostics=metric_diagnostics,
        source_text=source_text,
        source_language=source_language,
    )


def _metric_source_text(metric: dict[str, Any], source_text: str | None, source_language: str | None) -> str:
    if source_language == "bash":
        return _metric_source_header(metric, "#", source_language) + "\n" + (source_text or "")
    return _metric_source_header(metric, "--", source_language) + "\n" + (source_text or "")


def _metric_source_header(metric: dict[str, Any], comment_prefix: str, source_language: str | None) -> str:
    lines = [
        f"{comment_prefix} pg_diag metric: {metric.get('title') or '<untitled metric>'}",
    ]
    if metric.get("source_query"):
        lines.append(f"{comment_prefix} source_query: {metric['source_query']}")
    if metric.get("source_sampler"):
        lines.append(f"{comment_prefix} source_sampler: {metric['source_sampler']}")
    if metric.get("requires_collection"):
        lines.append(f"{comment_prefix} requires_collection: {metric['requires_collection']}")
    chart = metric.get("chart") or {}
    if chart:
        lines.append(f"{comment_prefix} chart: {chart.get('kind', 'line')} unit={chart.get('unit', '')}")
    if metric.get("partition_by"):
        lines.append(f"{comment_prefix} partition_by: {', '.join(metric.get('partition_by') or [])}")
    if metric.get("series"):
        lines.append(f"{comment_prefix} series:")
        for series in metric.get("series") or []:
            name = series.get("name") or series.get("name_from_ref") or series.get("value_ref") or "value"
            transform = series.get("transform") or "gauge"
            value_ref = series.get("value_ref") or series.get("name_from_ref") or ""
            unit = series.get("unit") or chart.get("unit") or ""
            color = f" color={series['color']}" if series.get("color") else ""
            adjustment = (
                f" delta_adjustment={series['delta_adjustment']}"
                if series.get("delta_adjustment") is not None else ""
            )
            lines.append(
                f"{comment_prefix}   - {name}: {transform}({value_ref}) "
                f"unit={unit}{adjustment}{color}"
            )
    if metric.get("top_n"):
        top_n = metric.get("top_n") or {}
        refs = top_n.get("value_refs") or ([top_n.get("value_ref")] if top_n.get("value_ref") else [])
        lines.append(
            f"{comment_prefix} top_n: mode={top_n.get('mode', 'interval')} "
            f"limit={top_n.get('limit', '')} transform={top_n.get('transform', 'rate')}"
        )
        if refs:
            lines.append(f"{comment_prefix} top_n.value_refs: {', '.join(str(ref) for ref in refs if ref)}")
        if top_n.get("numerator_refs") or top_n.get("denominator_refs") or top_n.get("denominator_ref"):
            numerator_refs = top_n.get("numerator_refs") or refs
            denominator_refs = top_n.get("denominator_refs") or [top_n.get("denominator_ref")]
            lines.append(f"{comment_prefix} top_n.numerator_refs: {', '.join(str(ref) for ref in numerator_refs if ref)}")
            lines.append(f"{comment_prefix} top_n.denominator_refs: {', '.join(str(ref) for ref in denominator_refs if ref)}")
    if metric.get("table"):
        table = metric.get("table") or {}
        lines.append(f"{comment_prefix} table_metric: mode={table.get('mode', 'first_last_delta')} limit={table.get('limit', '')}")
    if source_language == "bash":
        lines.append(f"{comment_prefix} sampler source follows")
    elif metric.get("requires_collection") == "window_endpoints":
        lines.append(f"{comment_prefix} window endpoint SQL source follows")
    else:
        lines.append(f"{comment_prefix} sampled SQL source follows")
    return "\n".join(lines)


def _sampler_source_text(source_sampler: str) -> str:
    scripts = {
        "os.cpu": """#!/usr/bin/env bash
# pg_diag threaded sampler: CPU utilization and load average.
cat /proc/stat
cat /proc/loadavg
""",
        "os.memory": """#!/usr/bin/env bash
# pg_diag threaded sampler: memory and swap usage.
cat /proc/meminfo
""",
        "os.disk": """#!/usr/bin/env bash
# pg_diag threaded sampler: disk throughput, IOPS, utilization and latency.
# The real interval/count are supplied by pg_diag snapshots settings.
iostat -dxk "$INTERVAL_SECONDS" "$SAMPLE_COUNT"
""",
        "os.network": """#!/usr/bin/env bash
# pg_diag threaded sampler: network receive/transmit bytes and packets.
cat /proc/net/dev
""",
        "os.backend_proc": """#!/usr/bin/env bash
# pg_diag window-endpoint sampler: per-PostgreSQL-process CPU, RSS and I/O counters.
# Process state is read once at window start and once at window end.
# /proc/<pid>/io may be unreadable for another OS user; pg_diag then reports io_access=false.
for pid_dir in /proc/[0-9]*; do
  cat "$pid_dir/comm" "$pid_dir/cmdline" "$pid_dir/stat" "$pid_dir/status" 2>/dev/null
  cat "$pid_dir/io" 2>/dev/null || true
done
""",
    }
    return scripts.get(
        source_sampler,
        f"""#!/usr/bin/env bash
# pg_diag threaded sampler source: {source_sampler}
# Implemented by pg_diag.os_metrics.
""",
    )


def _has_successful_source_item(items: list[dict[str, Any]]) -> bool:
    return any(item.get("collection_status") in {"ok", "empty"} for item in items)


def _source_health(
    items: list[dict[str, Any]],
) -> tuple[str | None, str | None, list[dict[str, Any]]]:
    statuses = Counter(str(item.get("collection_status") or "error") for item in items)
    failures = sum(statuses.get(status, 0) for status in ("error", "unsupported", "skipped"))
    if not failures:
        return None, None, []

    if statuses.get("error"):
        status = "error"
    elif statuses.get("unsupported"):
        status = "unsupported"
    else:
        status = "skipped"
    reason = next(
        (
            str(item.get("reason"))
            for item in items
            if item.get("collection_status") == status and item.get("reason")
        ),
        f"source samples include {failures} unsuccessful collection(s)",
    )
    level = "error" if not _has_successful_source_item(items) and status == "error" else "warning"
    diagnostic = {
        "level": level,
        "code": "metric_source_samples",
        "message": (
            f"Metric source samples: {dict(sorted(statuses.items()))}; "
            f"{failures} unsuccessful collection(s)"
        ),
    }
    return status, reason, [diagnostic]


def _sampler_failure_status(diagnostics: list[dict[str, Any]]) -> str:
    message = " ".join(str(item.get("message") or "") for item in diagnostics).lower()
    return "unsupported" if "not found" in message or "unavailable" in message else "error"


def build_chart_result(
    metric: dict[str, Any],
    samples: list[dict[str, Any]],
    semantic_columns: dict[str, dict[str, str]],
) -> dict[str, Any]:
    if metric.get("top_n"):
        return _build_top_n_chart_result(metric, samples, semantic_columns)

    raw_series: dict[str, dict[str, Any]] = {}
    sorted_samples = sorted(samples, key=lambda sample: str(sample.get("timestamp") or ""))
    sample_timestamps = [_sample_timestamp(sample) for sample in sorted_samples]
    partition_refs = metric.get("partition_by") or []

    for sample_index, sample in enumerate(sorted_samples):
        sample_timestamp = sample_timestamps[sample_index]
        for row in sample.get("rows") or []:
            timestamp = _row_timestamp(row, sample_timestamp)
            partition_values = [
                _string_value(_resolve_ref(row, semantic_columns, partition_ref))
                for partition_ref in partition_refs
            ]
            for series_def in metric.get("series") or []:
                value_ref = series_def.get("value_ref")
                if not value_ref:
                    continue
                value = _number_or_none(_resolve_ref(row, semantic_columns, value_ref))
                name = _series_name(row, semantic_columns, series_def, partition_values)
                raw = raw_series.setdefault(
                    name,
                    {
                        "name": name,
                        "unit": series_def.get("unit") or (metric.get("chart") or {}).get("unit"),
                        "color": series_def.get("color"),
                        "transform": series_def.get("transform") or "gauge",
                        "delta_adjustment": series_def.get("delta_adjustment") or 0,
                        "raw_points": {},
                    },
                )
                raw["raw_points"][sample_index] = {"t": timestamp, "value": value}

    series = []
    interval_counts: Counter[str] = Counter()
    for raw in raw_series.values():
        transform = raw.get("transform")
        if transform in {"rate", "delta"}:
            points, point_counts = _transform_interval_points(
                raw["raw_points"],
                sample_timestamps,
                transform,
                _number_or_none(raw.get("delta_adjustment")) or 0.0,
            )
            interval_counts.update(point_counts)
        else:
            points = [
                {"t": point["t"], "value": point["value"]}
                for _sample_index, point in sorted(raw["raw_points"].items())
            ]
        series.append(
            {
                "name": raw["name"],
                "unit": raw.get("unit"),
                "color": raw.get("color"),
                "points": points,
            }
        )

    chart = metric.get("chart") or {"kind": "line"}
    ordered_series = series if chart.get("series_order") == "configured" else sorted(series, key=lambda item: item["name"])
    result = {
        "kind": "chart",
        "chart": chart,
        "series": ordered_series,
        "sample_count": len(sorted_samples),
    }
    return _with_interval_coverage(result, interval_counts)


def _build_top_n_chart_result(
    metric: dict[str, Any],
    samples: list[dict[str, Any]],
    semantic_columns: dict[str, dict[str, str]],
) -> dict[str, Any]:
    top_n = metric.get("top_n") or {}
    sorted_samples = sorted(samples, key=lambda sample: str(sample.get("timestamp") or ""))
    chart = dict(metric.get("chart") or {"kind": "stacked_column"})
    if top_n.get("mode") == "first_last":
        chart["x_type"] = "datetime"
        series, interval_counts = _top_n_first_last_series(
            top_n,
            sorted_samples,
            semantic_columns,
            chart,
        )
    else:
        chart["x_type"] = "datetime"
        series, interval_counts = _top_n_interval_series(
            top_n,
            sorted_samples,
            semantic_columns,
            chart,
        )

    result = {
        "kind": "chart",
        "chart": chart,
        "series": series,
        "sample_count": len(sorted_samples),
    }
    return _with_interval_coverage(result, interval_counts)


def _top_n_interval_series(
    top_n: dict[str, Any],
    sorted_samples: list[dict[str, Any]],
    semantic_columns: dict[str, dict[str, str]],
    chart: dict[str, Any],
) -> tuple[list[dict[str, Any]], Counter[str]]:
    interval_counts: Counter[str] = Counter()
    if len(sorted_samples) < 2:
        return [], interval_counts

    key_refs = top_n.get("key_refs") or top_n.get("partition_by") or []
    limit = _positive_int(top_n.get("limit"), 10)
    drop_zero = top_n.get("drop_zero", True)
    series_by_label: dict[str, dict[str, Any]] = {}

    for previous, current in zip(sorted_samples, sorted_samples[1:]):
        previous_timestamp = _sample_timestamp(previous)
        current_timestamp = _sample_timestamp(current)
        previous_rows = _rows_by_key(previous.get("rows") or [], key_refs, semantic_columns)
        current_rows = _rows_by_key(current.get("rows") or [], key_refs, semantic_columns)
        candidates: list[tuple[float, str, str]] = []
        for key in sorted(set(previous_rows) | set(current_rows)):
            first_row = previous_rows.get(key)
            last_row = current_rows.get(key)
            if first_row is None:
                interval_counts[INTERVAL_MISSING_START] += 1
                continue
            if last_row is None:
                interval_counts[INTERVAL_MISSING_END] += 1
                continue
            interval_seconds = _row_interval_seconds(first_row, last_row, previous_timestamp, current_timestamp)
            if interval_seconds <= 0:
                interval_counts[INTERVAL_INVALID_INTERVAL] += 1
                continue
            interval_value = _top_n_metric_value(
                top_n,
                first_row,
                last_row,
                semantic_columns,
                interval_seconds,
            )
            interval_counts[interval_value.status] += 1
            value = interval_value.value
            if interval_value.status != INTERVAL_OK or value is None or (drop_zero and value <= 0):
                continue
            timestamp = _row_timestamp(last_row, current_timestamp)
            candidates.append((value, _top_n_label(top_n, key, last_row, semantic_columns), timestamp))

        candidates.sort(key=lambda item: (-item[0], item[1]))
        for value, label, timestamp in candidates[:limit]:
            series = series_by_label.setdefault(
                label,
                {
                    "name": label,
                    "unit": top_n.get("unit") or chart.get("unit"),
                    "points": [],
                    "_total": 0.0,
                },
            )
            series["points"].append({"t": timestamp, "value": round(value, 6)})
            series["_total"] += value

    series = _strip_private_series_keys(_order_top_n_series(series_by_label.values(), chart))
    return series, interval_counts


def _top_n_first_last_series(
    top_n: dict[str, Any],
    sorted_samples: list[dict[str, Any]],
    semantic_columns: dict[str, dict[str, str]],
    chart: dict[str, Any],
) -> tuple[list[dict[str, Any]], Counter[str]]:
    interval_counts: Counter[str] = Counter()
    if len(sorted_samples) < 2:
        return [], interval_counts

    first = sorted_samples[0]
    last = sorted_samples[-1]
    first_timestamp = _sample_timestamp(first)
    last_timestamp = _sample_timestamp(last)

    key_refs = top_n.get("key_refs") or top_n.get("partition_by") or []
    first_rows = _rows_by_key(first.get("rows") or [], key_refs, semantic_columns)
    last_rows = _rows_by_key(last.get("rows") or [], key_refs, semantic_columns)
    drop_zero = top_n.get("drop_zero", True)
    candidates: list[tuple[float, str, str]] = []
    for key in sorted(set(first_rows) | set(last_rows)):
        first_row = first_rows.get(key)
        last_row = last_rows.get(key)
        if first_row is None:
            interval_counts[INTERVAL_MISSING_START] += 1
            continue
        if last_row is None:
            interval_counts[INTERVAL_MISSING_END] += 1
            continue
        interval_seconds = _row_interval_seconds(first_row, last_row, first_timestamp, last_timestamp)
        if interval_seconds <= 0:
            interval_counts[INTERVAL_INVALID_INTERVAL] += 1
            continue
        interval_value = _top_n_metric_value(
            top_n,
            first_row,
            last_row,
            semantic_columns,
            interval_seconds,
        )
        interval_counts[interval_value.status] += 1
        value = interval_value.value
        if interval_value.status != INTERVAL_OK or value is None or (drop_zero and value <= 0):
            continue
        timestamp = _row_timestamp(last_row, last_timestamp)
        candidates.append((value, _top_n_label(top_n, key, last_row, semantic_columns), timestamp))

    candidates.sort(key=lambda item: (-item[0], item[1]))
    limit = _positive_int(top_n.get("limit"), 10)
    series = [
        {
            "name": label,
            "unit": top_n.get("unit") or chart.get("unit"),
            "points": [{"t": point_timestamp, "value": round(value, 6)}],
            "_total": value,
        }
        for value, label, point_timestamp in candidates[:limit]
    ]
    return _strip_private_series_keys(_order_top_n_series(series, chart)), interval_counts


def _order_top_n_series(series: Any, chart: dict[str, Any]) -> list[dict[str, Any]]:
    series_list = list(series)
    if chart.get("kind") == "stacked_column":
        return sorted(series_list, key=lambda item: (float(item.get("_total") or 0.0), str(item.get("name") or "")))
    return sorted(series_list, key=lambda item: (-float(item.get("_total") or 0.0), str(item.get("name") or "")))


def _top_n_metric_value(
    top_n: dict[str, Any],
    first_row: dict[str, Any] | None,
    last_row: dict[str, Any],
    semantic_columns: dict[str, dict[str, str]],
    interval_seconds: float,
) -> IntervalValue:
    operation = top_n.get("operation") or "sum"
    value_refs = _top_n_value_refs(top_n)
    if operation == "ratio":
        numerator_refs = top_n.get("numerator_refs") or value_refs
        denominator_refs = top_n.get("denominator_refs") or [top_n.get("denominator_ref")]
        numerator = _counter_delta_sum(
            first_row,
            last_row,
            semantic_columns,
            [str(ref) for ref in numerator_refs if ref],
        )
        if numerator.status != INTERVAL_OK:
            return numerator
        denominator = _counter_delta_sum(
            first_row,
            last_row,
            semantic_columns,
            [str(ref) for ref in denominator_refs if ref],
        )
        if denominator.status != INTERVAL_OK:
            return denominator
        if denominator.value is None or denominator.value <= 0:
            return IntervalValue(None, INTERVAL_NO_ACTIVITY)
        return IntervalValue(
            round(float(numerator.value or 0.0) / denominator.value, 6),
            INTERVAL_OK,
        )

    transform = top_n.get("transform") or "rate"
    values: list[float] = []
    for ref in value_refs:
        if not ref:
            continue
        if transform in {"delta", "rate"}:
            interval_value = _counter_delta_for_ref(
                first_row,
                last_row,
                semantic_columns,
                ref,
            )
            if interval_value.status != INTERVAL_OK or interval_value.value is None:
                return interval_value
            values.append(interval_value.value)
        elif transform == "avg":
            average = _average_for_ref(first_row, last_row, semantic_columns, ref)
            if average is None:
                return IntervalValue(None, INTERVAL_INVALID_VALUE)
            values.append(average)
        else:
            value = _number_or_none(_resolve_ref(last_row, semantic_columns, ref))
            if value is None:
                return IntervalValue(None, INTERVAL_INVALID_VALUE)
            values.append(value)
    value = sum(values)
    if transform == "rate":
        return IntervalValue(round(value / interval_seconds, 6), INTERVAL_OK)
    return IntervalValue(round(value, 6), INTERVAL_OK)


def _top_n_value_refs(top_n: dict[str, Any]) -> list[str]:
    if isinstance(top_n.get("value_refs"), list):
        return [str(ref) for ref in top_n["value_refs"] if ref]
    if top_n.get("value_ref"):
        return [str(top_n["value_ref"])]
    return []


def _counter_delta_for_ref(
    first_row: dict[str, Any] | None,
    last_row: dict[str, Any],
    semantic_columns: dict[str, dict[str, str]],
    ref: str,
) -> IntervalValue:
    first_value = _number_or_none(_resolve_ref(first_row or {}, semantic_columns, ref)) if first_row else None
    last_value = _number_or_none(_resolve_ref(last_row, semantic_columns, ref))
    return _counter_delta_value(first_value, last_value)


def _counter_delta_sum(
    first_row: dict[str, Any] | None,
    last_row: dict[str, Any],
    semantic_columns: dict[str, dict[str, str]],
    refs: list[str],
) -> IntervalValue:
    values: list[float] = []
    statuses: list[str] = []
    for ref in refs:
        interval_value = _counter_delta_for_ref(
            first_row,
            last_row,
            semantic_columns,
            ref,
        )
        statuses.append(interval_value.status)
        if interval_value.value is not None:
            values.append(interval_value.value)
    status = _combined_interval_status(statuses)
    if status != INTERVAL_OK:
        return IntervalValue(None, status)
    return IntervalValue(sum(values), INTERVAL_OK)


def _average_for_ref(
    first_row: dict[str, Any] | None,
    last_row: dict[str, Any],
    semantic_columns: dict[str, dict[str, str]],
    ref: str,
) -> float | None:
    last_value = _number_or_none(_resolve_ref(last_row, semantic_columns, ref))
    first_value = _number_or_none(_resolve_ref(first_row or {}, semantic_columns, ref)) if first_row else None
    if first_value is None or last_value is None:
        return None
    return (first_value + last_value) / 2.0


def _top_n_label(
    top_n: dict[str, Any],
    key: tuple[str, ...],
    row: dict[str, Any],
    semantic_columns: dict[str, dict[str, str]],
) -> str:
    label_refs = top_n.get("label_refs") or []
    if label_refs:
        parts = [_string_value(_resolve_ref(row, semantic_columns, ref)) for ref in label_refs]
    else:
        parts = list(key)
    label = ".".join(part for part in parts if part)
    return label or "<unknown>"


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _strip_private_series_keys(series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned = []
    for entry in series:
        cleaned.append({key: value for key, value in entry.items() if not key.startswith("_")})
    return cleaned


def build_table_result(
    metric: dict[str, Any],
    samples: list[dict[str, Any]],
    semantic_columns: dict[str, dict[str, str]],
    collection_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    table = metric.get("table") or {}
    sorted_samples = sorted(samples, key=lambda sample: str(sample.get("timestamp") or ""))
    columns = _table_columns(table)
    if table.get("mode") == "sample_sum":
        return _build_sample_sum_table(table, sorted_samples, semantic_columns, columns)
    if len(sorted_samples) < 2:
        return {"kind": "table", "columns": columns, "rows": [], "row_count": 0}

    first = sorted_samples[0]
    last = sorted_samples[-1]
    first_timestamp = _sample_timestamp(first)
    last_timestamp = _sample_timestamp(last)

    key_refs = table.get("key_refs") or table.get("partition_by") or []
    first_rows = _rows_by_key(first.get("rows") or [], key_refs, semantic_columns)
    last_rows = _rows_by_key(last.get("rows") or [], key_refs, semantic_columns)

    rows: list[list[Any]] = []
    interval_counts: Counter[str] = Counter()
    for key in sorted(set(first_rows) | set(last_rows)):
        first_row = first_rows.get(key)
        last_row = last_rows.get(key)
        if first_row is None:
            interval_counts[INTERVAL_MISSING_START] += 1
            continue
        if last_row is None:
            interval_counts[INTERVAL_MISSING_END] += 1
            continue
        interval_seconds = _row_interval_seconds(first_row, last_row, first_timestamp, last_timestamp)
        if interval_seconds <= 0:
            interval_counts[INTERVAL_INVALID_INTERVAL] += 1
            continue
        interval_status = _table_row_interval_status(
            table,
            first_row,
            last_row,
            semantic_columns,
        )
        interval_counts[interval_status] += 1
        if interval_status != INTERVAL_OK:
            continue
        rendered: list[Any] = []
        nonzero_metric = False
        for column in table.get("columns") or []:
            value = _table_column_value(
                column,
                key,
                first_row,
                last_row,
                semantic_columns,
                interval_seconds,
                collection_context,
            )
            rendered.append(value)
            if column.get("role") != "key" and isinstance(value, (int, float)) and value != 0:
                nonzero_metric = True
        if table.get("drop_zero_rows", True) and not nonzero_metric:
            continue
        rows.append(rendered)

    rows = _sort_table_rows(rows, columns, table.get("sort") or {})
    limit = table.get("limit")
    if isinstance(limit, int) and limit > 0:
        rows = rows[:limit]
    result = {"kind": "table", "columns": columns, "rows": rows, "row_count": len(rows)}
    return _with_interval_coverage(result, interval_counts)


def _build_sample_sum_table(
    table: dict[str, Any],
    sorted_samples: list[dict[str, Any]],
    semantic_columns: dict[str, dict[str, str]],
    columns: list[dict[str, Any]],
) -> dict[str, Any]:
    key_refs = table.get("key_refs") or table.get("partition_by") or []
    groups: dict[tuple[str, ...], dict[str, Any]] = {}
    for sample in sorted_samples:
        for row in sample.get("rows") or []:
            key = tuple(_string_value(_resolve_ref(row, semantic_columns, ref)) for ref in key_refs)
            if not key:
                continue
            group = groups.setdefault(key, {"rows": [], "last": row})
            group["rows"].append(row)
            group["last"] = row

    rendered_rows: list[list[Any]] = []
    for key in sorted(groups):
        group = groups[key]
        rendered: list[Any] = []
        nonzero_metric = False
        for column in table.get("columns") or []:
            value = _sample_sum_column_value(column, key, group["rows"], group["last"], semantic_columns)
            rendered.append(value)
            if column.get("role") != "key" and isinstance(value, (int, float)) and value != 0:
                nonzero_metric = True
        if table.get("drop_zero_rows", True) and not nonzero_metric:
            continue
        rendered_rows.append(rendered)

    rendered_rows = _sort_table_rows(rendered_rows, columns, table.get("sort") or {})
    limit = table.get("limit")
    if isinstance(limit, int) and limit > 0:
        rendered_rows = rendered_rows[:limit]
    return {"kind": "table", "columns": columns, "rows": rendered_rows, "row_count": len(rendered_rows)}


def _sample_sum_column_value(
    column: dict[str, Any],
    key: tuple[str, ...],
    rows: list[dict[str, Any]],
    last_row: dict[str, Any],
    semantic_columns: dict[str, dict[str, str]],
) -> Any:
    if column.get("role") == "key":
        key_index = int(column.get("key_index") or 0)
        return key[key_index] if key_index < len(key) else ""

    ref = column.get("value_ref") or column.get("ref")
    transform = column.get("transform") or "last"
    values = [_number_or_none(_resolve_ref(row, semantic_columns, ref)) for row in rows] if ref else []
    numeric_values = [value for value in values if value is not None]
    if transform == "sample_count":
        return len(rows)
    if transform == "sum":
        return round(sum(numeric_values), 6)
    if transform == "avg":
        return round(sum(numeric_values) / len(numeric_values), 6) if numeric_values else 0.0
    if transform == "max":
        return max(numeric_values) if numeric_values else 0.0
    if transform == "last":
        return _resolve_ref(last_row, semantic_columns, ref) if ref else None
    return _resolve_ref(last_row, semantic_columns, ref) if ref else None


def _table_columns(table: dict[str, Any]) -> list[dict[str, Any]]:
    columns = []
    for column in table.get("columns") or []:
        columns.append({"name": column.get("name") or column.get("ref") or "value", "pg_type": column.get("pg_type") or ""})
    return columns


def evaluate_metric_table_findings(
    result: dict[str, Any],
    evaluation: dict[str, Any],
) -> tuple[str | None, dict[str, Any]]:
    rules = evaluation.get("rules") or []
    if not rules:
        return None, {}

    column_names = [str(column.get("name") or "") for column in result.get("columns") or []]
    findings: list[tuple[str, str]] = []
    for row in result.get("rows") or []:
        values = {
            name: row[index] if index < len(row) else None
            for index, name in enumerate(column_names)
        }
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            severity = str(rule.get("severity") or "").lower()
            conditions = rule.get("all") or []
            if severity not in {"medium", "high"} or not conditions:
                continue
            if all(_metric_evaluation_condition_matches(values, condition) for condition in conditions):
                findings.append((severity, str(rule.get("reason") or "Review derived metric values")))

    if not findings:
        return "ok", {}
    severity_level = max(findings, key=lambda finding: SEVERITY_LEVEL_RANK[finding[0]])[0]
    reasons = list(dict.fromkeys(reason for _severity, reason in findings if reason))
    description = f"{len(findings)} finding row(s); highest severity is {severity_level}."
    if reasons:
        description += " " + "; ".join(reasons[:3])
    return severity_level, {
        "summary": {
            "severity": severity_level,
            "status": "fail" if severity_level == "high" else "review",
            "title": str(evaluation.get("summary_title") or "Derived metric findings require review"),
            "description": description,
            "recommendation": str(
                evaluation.get("recommendation")
                or "Review the derived rows and item instruction before remediation."
            ),
        },
        "items": [],
    }


def _metric_evaluation_condition_matches(
    values: dict[str, Any],
    condition: Any,
) -> bool:
    if not isinstance(condition, dict):
        return False
    actual = _number_or_none(values.get(str(condition.get("column") or "")))
    expected = _number_or_none(condition.get("value"))
    if actual is None or expected is None:
        return False
    operator = str(condition.get("operator") or "")
    if operator == "gt":
        return actual > expected
    if operator == "gte":
        return actual >= expected
    if operator == "lt":
        return actual < expected
    if operator == "lte":
        return actual <= expected
    if operator == "eq":
        return actual == expected
    return False


def _rows_by_key(
    rows: list[dict[str, Any]],
    key_refs: list[str],
    semantic_columns: dict[str, dict[str, str]],
) -> dict[tuple[str, ...], dict[str, Any]]:
    keyed: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        key = tuple(_string_value(_resolve_ref(row, semantic_columns, ref)) for ref in key_refs)
        if key:
            keyed[key] = row
    return keyed


def _table_column_value(
    column: dict[str, Any],
    key: tuple[str, ...],
    first_row: dict[str, Any] | None,
    last_row: dict[str, Any],
    semantic_columns: dict[str, dict[str, str]],
    interval_seconds: float,
    collection_context: dict[str, Any] | None = None,
) -> Any:
    role = column.get("role")
    if role == "key":
        key_index = int(column.get("key_index") or 0)
        return key[key_index] if key_index < len(key) else ""

    ref = column.get("value_ref") or column.get("ref")
    transform = column.get("transform") or "last"
    if transform == "context":
        return (collection_context or {}).get(str(column.get("context_key") or ""))
    last_value = _number_or_none(_resolve_ref(last_row, semantic_columns, ref)) if ref else None
    first_value = _number_or_none(_resolve_ref(first_row or {}, semantic_columns, ref)) if ref and first_row else None

    if transform in {"delta_minus_context", "rate_minus_context"}:
        delta = _counter_delta_value(first_value, last_value).value
        adjustment = _number_or_none(
            (collection_context or {}).get(str(column.get("context_key") or ""))
        )
        if delta is None or adjustment is None or delta < adjustment:
            return None
        adjusted = delta - adjustment
        if transform == "rate_minus_context":
            return round(adjusted / interval_seconds, 6) if interval_seconds > 0 else None
        return adjusted

    if transform == "last":
        resolved = _resolve_ref(last_row, semantic_columns, ref) if ref else None
        return resolved
    if transform == "first":
        resolved = _resolve_ref(first_row or {}, semantic_columns, ref) if ref and first_row else None
        return resolved
    if transform == "delta":
        return _counter_delta_value(first_value, last_value).value
    if transform == "rate":
        delta = _counter_delta_value(first_value, last_value).value
        return round(delta / interval_seconds, 6) if delta is not None else None
    if transform == "pct_delta":
        previous = first_value or 0.0
        delta = _counter_delta_value(first_value, last_value).value
        return round(delta * 100.0 / previous, 3) if delta is not None and previous > 0 else None
    return _resolve_ref(last_row, semantic_columns, ref) if ref else None


def _counter_delta_value(
    first_value: float | None,
    last_value: float | None,
) -> IntervalValue:
    if first_value is None or last_value is None:
        return IntervalValue(None, INTERVAL_INVALID_VALUE)
    if last_value < first_value:
        return IntervalValue(None, INTERVAL_COUNTER_DECREASE)
    return IntervalValue(round(last_value - first_value, 6), INTERVAL_OK)


def _table_row_interval_status(
    table: dict[str, Any],
    first_row: dict[str, Any],
    last_row: dict[str, Any],
    semantic_columns: dict[str, dict[str, str]],
) -> str:
    statuses: list[str] = []
    for ref in table.get("epoch_refs") or []:
        first_epoch = _resolve_ref(first_row, semantic_columns, ref)
        last_epoch = _resolve_ref(last_row, semantic_columns, ref)
        if first_epoch in (None, "") and last_epoch in (None, ""):
            continue
        if first_epoch in (None, "") or last_epoch in (None, ""):
            statuses.append(INTERVAL_INVALID_VALUE)
            continue
        if str(first_epoch) != str(last_epoch):
            statuses.append(INTERVAL_EPOCH_CHANGED)
    for column in table.get("columns") or []:
        if column.get("transform") not in {
            "delta", "rate", "pct_delta", "delta_minus_context", "rate_minus_context"
        }:
            continue
        ref = column.get("value_ref") or column.get("ref")
        if not ref:
            statuses.append(INTERVAL_INVALID_VALUE)
            continue
        first_value = _number_or_none(_resolve_ref(first_row, semantic_columns, ref))
        last_value = _number_or_none(_resolve_ref(last_row, semantic_columns, ref))
        statuses.append(_counter_delta_value(first_value, last_value).status)
    return _combined_interval_status(statuses)


def _combined_interval_status(statuses: list[str]) -> str:
    if not statuses:
        return INTERVAL_OK
    for status in (
        INTERVAL_EPOCH_CHANGED,
        INTERVAL_COUNTER_DECREASE,
        INTERVAL_INVALID_VALUE,
        INTERVAL_INVALID_INTERVAL,
        INTERVAL_MISSING_START,
        INTERVAL_MISSING_END,
        INTERVAL_NO_ACTIVITY,
    ):
        if status in statuses:
            return status
    return INTERVAL_OK


def _with_interval_coverage(
    result: dict[str, Any],
    counts: Counter[str],
) -> dict[str, Any]:
    coverage = interval_coverage_totals(counts)
    if coverage["total"] <= 0:
        return result
    result["interval_coverage"] = {
        **coverage,
        "counts": {
            status: counts[status]
            for status in INTERVAL_STATUS_ORDER
            if counts.get(status, 0) > 0
        },
    }
    return result


def _interval_coverage_feedback(
    result: dict[str, Any],
) -> tuple[str | None, dict[str, Any] | None]:
    coverage = result.get("interval_coverage") or {}
    invalid = int(coverage.get("invalid") or 0)
    counts = coverage.get("counts") or {}
    if invalid > 0:
        invalid_parts = [
            f"{status}={counts.get(status, 0)}"
            for status in (
                INTERVAL_EPOCH_CHANGED,
                INTERVAL_COUNTER_DECREASE,
                INTERVAL_INVALID_VALUE,
                INTERVAL_INVALID_INTERVAL,
            )
            if counts.get(status, 0)
        ]
        message = (
            f"{invalid} interval value(s) could not be calculated and were omitted"
            + (f" ({', '.join(invalid_parts)})" if invalid_parts else "")
        )
        return message, {
            "level": "warning",
            "code": "metric_interval_coverage",
            "message": message,
        }

    comparable = int(coverage.get("comparable") or 0)
    unmatched = int(coverage.get("unmatched") or 0)
    has_output = bool(result.get("rows")) if result.get("kind") == "table" else _chart_has_points(result)
    if comparable == 0 and unmatched > 0 and not has_output:
        return (
            "No keys were present in both limited endpoint selections; "
            "the row set may legitimately differ between samples",
            None,
        )
    return None, None


def _sort_table_rows(rows: list[list[Any]], columns: list[dict[str, Any]], sort: dict[str, Any]) -> list[list[Any]]:
    column_name = sort.get("column")
    direction = sort.get("direction") if sort.get("direction") in {"asc", "desc"} else "desc"
    if not column_name:
        return rows
    column_index = next((idx for idx, column in enumerate(columns) if column.get("name") == column_name), -1)
    if column_index < 0:
        return rows

    def key(row: list[Any]) -> tuple[int, Any]:
        value = row[column_index] if column_index < len(row) else None
        if isinstance(value, (int, float)):
            return (0, value)
        return (1, "" if value is None else str(value))

    return sorted(rows, key=key, reverse=direction == "desc")


def _rows_from_item(
    item: dict[str, Any] | None,
    fallback_columns: list[Any] | None = None,
) -> list[dict[str, Any]]:
    if not item:
        return []
    result = item.get("result") or {}
    if result.get("kind") != "table":
        return []
    raw_columns = result.get("columns") or fallback_columns or []
    columns = [
        column.get("name") if isinstance(column, dict) else str(column)
        for column in raw_columns
    ]
    rows = []
    for raw_row in result.get("rows") or []:
        rows.append({column: raw_row[index] if index < len(raw_row) else None for index, column in enumerate(columns)})
    return rows


def _sample_timestamp(sample: dict[str, Any]) -> str:
    fallback = str(sample.get("timestamp") or "")
    for row in sample.get("rows") or []:
        timestamp = _row_timestamp(row, "")
        if timestamp:
            return timestamp
    return fallback


def _row_timestamp(row: dict[str, Any], fallback: str) -> str:
    value = row.get(SNAPSHOT_TIME_COLUMN)
    return str(value) if value not in (None, "") else fallback


def _row_interval_seconds(
    first_row: dict[str, Any] | None,
    last_row: dict[str, Any],
    first_fallback: str,
    last_fallback: str,
) -> float:
    first_timestamp = _row_timestamp(first_row or {}, first_fallback) if first_row else first_fallback
    last_timestamp = _row_timestamp(last_row, last_fallback)
    return _seconds_between(first_timestamp, last_timestamp)


def _resolve_ref(row: dict[str, Any], semantic_columns: dict[str, dict[str, str]], ref: str) -> Any:
    parts = ref.split(".", 1)
    if len(parts) == 2:
        column = (semantic_columns.get(parts[0]) or {}).get(parts[1])
        if column:
            return row.get(column)
    return row.get(ref)


def _series_name(
    row: dict[str, Any],
    semantic_columns: dict[str, dict[str, str]],
    series_def: dict[str, Any],
    partition_values: list[str],
) -> str:
    if series_def.get("name_from_ref"):
        base = _string_value(_resolve_ref(row, semantic_columns, series_def["name_from_ref"]))
    else:
        base = str(series_def.get("name") or series_def.get("value_ref") or "value")
    suffix = [value for value in partition_values if value and value != base]
    if suffix:
        return f"{base} ({', '.join(suffix)})"
    return base


def _transform_interval_points(
    raw_points: dict[int, dict[str, Any]],
    sample_timestamps: list[str],
    transform: str,
    delta_adjustment: float = 0.0,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    points: list[dict[str, Any]] = []
    interval_counts: Counter[str] = Counter()
    previous: dict[str, Any] | None = None
    seen = False
    for sample_index, sample_timestamp in enumerate(sample_timestamps):
        point = raw_points.get(sample_index)
        if point is None:
            if previous is not None:
                interval_counts[INTERVAL_MISSING_END] += 1
                points.append({"t": sample_timestamp, "value": None})
            previous = None
            continue

        if not seen:
            points.append({"t": point["t"], "value": None})
            if sample_index > 0:
                interval_counts[INTERVAL_MISSING_START] += 1
            seen = True
            previous = point
            continue

        if previous is None:
            interval_counts[INTERVAL_MISSING_START] += 1
            points.append({"t": point["t"], "value": None})
            previous = point
            continue

        seconds = _seconds_between(str(previous["t"]), str(point["t"]))
        if seconds <= 0:
            interval_counts[INTERVAL_INVALID_INTERVAL] += 1
            points.append({"t": point["t"], "value": None})
        else:
            interval_value = _counter_delta_value(
                _number_or_none(previous.get("value")),
                _number_or_none(point.get("value")),
            )
            interval_counts[interval_value.status] += 1
            if interval_value.status != INTERVAL_OK or interval_value.value is None:
                points.append({"t": point["t"], "value": None})
            else:
                adjusted_delta = max(interval_value.value - max(delta_adjustment, 0.0), 0.0)
                transformed = (
                    adjusted_delta / seconds
                    if transform == "rate"
                    else adjusted_delta
                )
                points.append({"t": point["t"], "value": round(transformed, 6)})
        previous = point
    return points, interval_counts


def _seconds_between(start: str, end: str) -> float:
    try:
        return max((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds(), 0.0)
    except ValueError:
        return 0.0


def _number_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_value(value: Any) -> str:
    return "" if value is None else str(value)


def _empty_chart(metric: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "chart",
        "chart": metric.get("chart") or {"kind": "line"},
        "series": [],
        "sample_count": 0,
    }


def _empty_metric_result(metric: dict[str, Any]) -> dict[str, Any]:
    if metric.get("result") == "table" or metric.get("table"):
        return {
            "kind": "table",
            "columns": _table_columns(metric.get("table") or {}),
            "rows": [],
            "row_count": 0,
        }
    return _empty_chart(metric)


def _chart_has_points(chart: dict[str, Any]) -> bool:
    for series in chart.get("series") or []:
        for point in series.get("points") or []:
            if point.get("value") is not None:
                return True
    return False
