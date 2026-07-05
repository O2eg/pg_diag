"""Build chart payloads from repeated SQL and OS metric samples."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pg_diag.artifact import item_from_plan
from pg_diag.planner import PlannedItem


SNAPSHOT_TIME_COLUMN = "snapshot_time"


def build_metric_item(
    planned: PlannedItem,
    metric: dict[str, Any],
    db_snapshots: list[dict[str, Any]],
    os_samples: dict[str, list[dict[str, Any]]],
    source_item_by_query: dict[str, str],
    source_metadata_by_item: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    source_query = metric.get("source_query")
    source_sampler = metric.get("source_sampler")
    source_text: str | None = None
    source_language: str | None = None
    if source_query:
        source_item_id = source_item_by_query.get(source_query)
        if not source_item_id:
            return item_from_plan(
                planned,
                status="empty",
                reason=f"source query {source_query} was not collected",
                result=_empty_chart(metric),
            )
        samples = [
            {
                "timestamp": snapshot["timestamp"],
                "rows": _rows_from_item(snapshot.get("items", {}).get(source_item_id)),
            }
            for snapshot in db_snapshots
        ]
        source_metadata = source_metadata_by_item.get(source_item_id, {})
        semantic_columns = source_metadata.get("semantic_columns") or {}
        source_text = source_metadata.get("source_text")
        source_language = source_metadata.get("source_language") or "sql"
    elif source_sampler:
        samples = os_samples.get(source_sampler, [])
        semantic_columns = {}
        source_text = _sampler_source_text(source_sampler)
        source_language = "bash"
    else:
        return item_from_plan(
            planned,
            status="empty",
            reason="metric has no source",
            result=_empty_chart(metric),
        )

    source_text = _metric_source_text(metric, source_text, source_language) if source_text else None

    if metric.get("result") == "table" or metric.get("table"):
        table = build_table_result(metric, samples, semantic_columns)
        status = "ok" if table.get("rows") else "empty"
        return item_from_plan(planned, status=status, result=table, source_text=source_text, source_language=source_language)

    chart = build_chart_result(metric, samples, semantic_columns)
    status = "ok" if _chart_has_points(chart) else "empty"
    return item_from_plan(planned, status=status, result=chart, source_text=source_text, source_language=source_language)


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
            lines.append(f"{comment_prefix}   - {name}: {transform}({value_ref}) unit={unit}{color}")
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
# pg_diag threaded sampler: per-PostgreSQL-process CPU, RSS and I/O counters.
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


def build_chart_result(
    metric: dict[str, Any],
    samples: list[dict[str, Any]],
    semantic_columns: dict[str, dict[str, str]],
) -> dict[str, Any]:
    if metric.get("top_n"):
        return _build_top_n_chart_result(metric, samples, semantic_columns)

    raw_series: dict[str, dict[str, Any]] = {}
    sorted_samples = sorted(samples, key=lambda sample: str(sample.get("timestamp") or ""))
    partition_refs = metric.get("partition_by") or []

    for sample in sorted_samples:
        sample_timestamp = _sample_timestamp(sample)
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
                        "raw_points": [],
                    },
                )
                raw["raw_points"].append({"t": timestamp, "value": value})

    series = []
    for raw in raw_series.values():
        series.append(
            {
                "name": raw["name"],
                "unit": raw.get("unit"),
                "color": raw.get("color"),
                "points": _transform_points(raw["raw_points"], raw.get("transform")),
            }
        )

    chart = metric.get("chart") or {"kind": "line"}
    ordered_series = series if chart.get("series_order") == "configured" else sorted(series, key=lambda item: item["name"])
    return {
        "kind": "chart",
        "chart": chart,
        "series": ordered_series,
        "sample_count": len(sorted_samples),
    }


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
        series = _top_n_first_last_series(top_n, sorted_samples, semantic_columns, chart)
    else:
        chart["x_type"] = "datetime"
        series = _top_n_interval_series(top_n, sorted_samples, semantic_columns, chart)

    return {
        "kind": "chart",
        "chart": chart,
        "series": series,
        "sample_count": len(sorted_samples),
    }


def _top_n_interval_series(
    top_n: dict[str, Any],
    sorted_samples: list[dict[str, Any]],
    semantic_columns: dict[str, dict[str, str]],
    chart: dict[str, Any],
) -> list[dict[str, Any]]:
    if len(sorted_samples) < 2:
        return []

    key_refs = top_n.get("key_refs") or top_n.get("partition_by") or []
    limit = _positive_int(top_n.get("limit"), 10)
    drop_zero = top_n.get("drop_zero", True)
    series_by_label: dict[str, dict[str, Any]] = {}

    for previous, current in zip(sorted_samples, sorted_samples[1:]):
        previous_timestamp = _sample_timestamp(previous)
        timestamp = _sample_timestamp(current)
        interval_seconds = _seconds_between(previous_timestamp, timestamp)
        if interval_seconds <= 0:
            continue
        previous_rows = _rows_by_key(previous.get("rows") or [], key_refs, semantic_columns)
        current_rows = _rows_by_key(current.get("rows") or [], key_refs, semantic_columns)
        candidates: list[tuple[float, str]] = []
        for key in sorted(current_rows):
            last_row = current_rows[key]
            first_row = previous_rows.get(key)
            value = _top_n_metric_value(top_n, first_row, last_row, semantic_columns, interval_seconds)
            if value is None or (drop_zero and value <= 0):
                continue
            candidates.append((value, _top_n_label(top_n, key, last_row, semantic_columns)))

        candidates.sort(key=lambda item: (-item[0], item[1]))
        for value, label in candidates[:limit]:
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

    return _strip_private_series_keys(
        sorted(series_by_label.values(), key=lambda item: (-float(item.get("_total") or 0.0), str(item.get("name") or "")))
    )


def _top_n_first_last_series(
    top_n: dict[str, Any],
    sorted_samples: list[dict[str, Any]],
    semantic_columns: dict[str, dict[str, str]],
    chart: dict[str, Any],
) -> list[dict[str, Any]]:
    if len(sorted_samples) < 2:
        return []

    first = sorted_samples[0]
    last = sorted_samples[-1]
    first_timestamp = _sample_timestamp(first)
    last_timestamp = _sample_timestamp(last)
    interval_seconds = _seconds_between(first_timestamp, last_timestamp)
    if interval_seconds <= 0:
        return []

    key_refs = top_n.get("key_refs") or top_n.get("partition_by") or []
    first_rows = _rows_by_key(first.get("rows") or [], key_refs, semantic_columns)
    last_rows = _rows_by_key(last.get("rows") or [], key_refs, semantic_columns)
    drop_zero = top_n.get("drop_zero", True)
    candidates: list[tuple[float, str]] = []
    for key in sorted(last_rows):
        last_row = last_rows[key]
        value = _top_n_metric_value(top_n, first_rows.get(key), last_row, semantic_columns, interval_seconds)
        if value is None or (drop_zero and value <= 0):
            continue
        candidates.append((value, _top_n_label(top_n, key, last_row, semantic_columns)))

    candidates.sort(key=lambda item: (-item[0], item[1]))
    limit = _positive_int(top_n.get("limit"), 10)
    return [
        {
            "name": label,
            "unit": top_n.get("unit") or chart.get("unit"),
            "points": [{"t": last_timestamp, "value": round(value, 6)}],
        }
        for value, label in candidates[:limit]
    ]


def _top_n_metric_value(
    top_n: dict[str, Any],
    first_row: dict[str, Any] | None,
    last_row: dict[str, Any],
    semantic_columns: dict[str, dict[str, str]],
    interval_seconds: float,
) -> float | None:
    operation = top_n.get("operation") or "sum"
    value_refs = _top_n_value_refs(top_n)
    if operation == "ratio":
        numerator_refs = top_n.get("numerator_refs") or value_refs
        denominator_refs = top_n.get("denominator_refs") or [top_n.get("denominator_ref")]
        numerator = sum(_counter_delta_for_ref(first_row, last_row, semantic_columns, ref) for ref in numerator_refs if ref)
        denominator = sum(_counter_delta_for_ref(first_row, last_row, semantic_columns, ref) for ref in denominator_refs if ref)
        if denominator <= 0:
            return None
        return round(numerator / denominator, 6)

    transform = top_n.get("transform") or "rate"
    values = []
    for ref in value_refs:
        if not ref:
            continue
        if transform in {"delta", "rate"}:
            values.append(_counter_delta_for_ref(first_row, last_row, semantic_columns, ref))
        elif transform == "avg":
            values.append(_average_for_ref(first_row, last_row, semantic_columns, ref))
        else:
            values.append(_number_or_none(_resolve_ref(last_row, semantic_columns, ref)) or 0.0)
    value = sum(values)
    if transform == "rate":
        return round(value / interval_seconds, 6)
    return round(value, 6)


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
) -> float:
    first_value = _number_or_none(_resolve_ref(first_row or {}, semantic_columns, ref)) if first_row else None
    last_value = _number_or_none(_resolve_ref(last_row, semantic_columns, ref))
    return _counter_delta(first_value, last_value)


def _average_for_ref(
    first_row: dict[str, Any] | None,
    last_row: dict[str, Any],
    semantic_columns: dict[str, dict[str, str]],
    ref: str,
) -> float:
    last_value = _number_or_none(_resolve_ref(last_row, semantic_columns, ref))
    first_value = _number_or_none(_resolve_ref(first_row or {}, semantic_columns, ref)) if first_row else None
    values = [value for value in (first_value, last_value) if value is not None]
    return sum(values) / len(values) if values else 0.0


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
    interval_seconds = _seconds_between(_sample_timestamp(first), _sample_timestamp(last))
    if interval_seconds <= 0:
        interval_seconds = 1.0

    key_refs = table.get("key_refs") or table.get("partition_by") or []
    first_rows = _rows_by_key(first.get("rows") or [], key_refs, semantic_columns)
    last_rows = _rows_by_key(last.get("rows") or [], key_refs, semantic_columns)

    rows: list[list[Any]] = []
    for key in sorted(last_rows):
        last_row = last_rows[key]
        first_row = first_rows.get(key)
        rendered: list[Any] = []
        nonzero_metric = False
        for column in table.get("columns") or []:
            value = _table_column_value(column, key, first_row, last_row, semantic_columns, interval_seconds)
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
    return {"kind": "table", "columns": columns, "rows": rows, "row_count": len(rows)}


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
) -> Any:
    role = column.get("role")
    if role == "key":
        key_index = int(column.get("key_index") or 0)
        return key[key_index] if key_index < len(key) else ""

    ref = column.get("value_ref") or column.get("ref")
    transform = column.get("transform") or "last"
    last_value = _number_or_none(_resolve_ref(last_row, semantic_columns, ref)) if ref else None
    first_value = _number_or_none(_resolve_ref(first_row or {}, semantic_columns, ref)) if ref and first_row else None

    if transform == "last":
        resolved = _resolve_ref(last_row, semantic_columns, ref) if ref else None
        return resolved
    if transform == "first":
        resolved = _resolve_ref(first_row or {}, semantic_columns, ref) if ref and first_row else None
        return resolved
    if transform == "delta":
        return _counter_delta(first_value, last_value)
    if transform == "rate":
        return round(_counter_delta(first_value, last_value) / interval_seconds, 6)
    if transform == "pct_delta":
        previous = first_value or 0.0
        delta = _counter_delta(first_value, last_value)
        return round(delta * 100.0 / previous, 3) if previous > 0 else None
    return _resolve_ref(last_row, semantic_columns, ref) if ref else None


def _counter_delta(first_value: float | None, last_value: float | None) -> float:
    if first_value is None or last_value is None:
        return 0.0
    if last_value < first_value:
        return 0.0
    return round(last_value - first_value, 6)


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


def _rows_from_item(item: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not item:
        return []
    result = item.get("result") or {}
    if result.get("kind") != "table":
        return []
    columns = [column.get("name") if isinstance(column, dict) else str(column) for column in result.get("columns") or []]
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


def _transform_points(raw_points: list[dict[str, Any]], transform: str | None) -> list[dict[str, Any]]:
    if transform not in {"rate", "delta"}:
        return [{"t": point["t"], "value": point["value"]} for point in raw_points]

    points: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for point in raw_points:
        value = point["value"]
        if previous is None or value is None or previous.get("value") is None:
            points.append({"t": point["t"], "value": None})
            previous = point
            continue
        seconds = _seconds_between(str(previous["t"]), str(point["t"]))
        if seconds <= 0 or value < previous["value"]:
            points.append({"t": point["t"], "value": None})
        else:
            delta = value - previous["value"]
            transformed = delta / seconds if transform == "rate" else delta
            points.append({"t": point["t"], "value": round(transformed, 6)})
        previous = point
    return points


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


def _chart_has_points(chart: dict[str, Any]) -> bool:
    for series in chart.get("series") or []:
        for point in series.get("points") or []:
            if point.get("value") is not None:
                return True
    return False
