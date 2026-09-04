from __future__ import annotations

from pathlib import Path

from pg_diag.content_loader import load_content
from pg_diag.metric_engine import build_chart_result
from pg_diag.presentation import apply_presentation_contract
from pg_diag.sql_lint import lint_sql
from pg_diag.versioning import select_query_variant

# Item key -> metric id, source id, chart kind, chart unit,
# and every series as (transform, unit, quantity, optional).
CHARTS = {
    "checkpoint_trigger_events": (
        "checkpoints.trigger_events",
        "metrics.checkpoint_trigger_events",
        "column",
        "count",
        {
            "timed": ("delta", "count", "events", False),
            "requested": ("delta", "count", "events", False),
            "completed": ("delta", "count", "events", True),
        },
    ),
    "buffer_writes_by_process": (
        "checkpoints.buffer_writes_by_process",
        "metrics.buffer_writes_by_process",
        "stacked_area",
        "bytes/s",
        {
            "checkpointer": ("rate", "bytes/s", None, False),
            "background writer": ("rate", "bytes/s", None, False),
            "backends": ("rate", "bytes/s", None, False),
        },
    ),
    "checkpoint_write_sync_time_delta": (
        "checkpoints.write_sync_time_delta",
        "metrics.checkpoint_write_sync_time",
        "stacked_column",
        "ms",
        {
            "write": ("delta", "ms", None, False),
            "sync": ("delta", "ms", None, False),
        },
    ),
    "writer_pressure_events": (
        "checkpoints.writer_pressure_events",
        "metrics.writer_pressure_events",
        "column",
        "count",
        {
            "bgwriter stops": ("delta", "count", "events", False),
            "backend fsyncs": ("delta", "count", "events", False),
        },
    ),
    "buffer_allocation_rate": (
        "checkpoints.buffer_allocation_rate",
        "metrics.buffer_allocation_rate",
        "line",
        "blocks/s",
        {
            "allocated": ("rate", "blocks/s", None, False),
            "cleaned by bgwriter": ("rate", "blocks/s", None, False),
        },
    ),
    "restartpoint_events": (
        "checkpoints.restartpoint_events",
        "metrics.restartpoint_events",
        "column",
        "count",
        {
            "timed": ("delta", "count", "restartpoints", False),
            "requested": ("delta", "count", "restartpoints", False),
            "done": ("delta", "count", "restartpoints", False),
        },
    ),
}

VARIANTS = {
    "metrics.checkpoint_trigger_events": {
        100000: "metrics_checkpoint_trigger_events_pg10_pg16",
        160000: "metrics_checkpoint_trigger_events_pg10_pg16",
        170000: "metrics_checkpoint_trigger_events_pg17",
        180000: "metrics_checkpoint_trigger_events_pg18_plus",
    },
    "metrics.buffer_writes_by_process": {
        100000: "metrics_buffer_writes_by_process_pg10_pg16",
        160000: "metrics_buffer_writes_by_process_pg10_pg16",
        170000: "metrics_buffer_writes_by_process_pg17",
        180000: "metrics_buffer_writes_by_process_pg18_plus",
    },
    "metrics.checkpoint_write_sync_time": {
        100000: "metrics_checkpoint_write_sync_time_pg10_pg16",
        160000: "metrics_checkpoint_write_sync_time_pg10_pg16",
        170000: "metrics_checkpoint_write_sync_time_pg17_plus",
        180000: "metrics_checkpoint_write_sync_time_pg17_plus",
    },
    "metrics.writer_pressure_events": {
        100000: "metrics_writer_pressure_events_pg10_pg16",
        160000: "metrics_writer_pressure_events_pg10_pg16",
        170000: "metrics_writer_pressure_events_pg17_plus",
        180000: "metrics_writer_pressure_events_pg17_plus",
    },
    "metrics.buffer_allocation_rate": {
        100000: "metrics_buffer_allocation_rate_pg10_plus",
        160000: "metrics_buffer_allocation_rate_pg10_plus",
        170000: "metrics_buffer_allocation_rate_pg10_plus",
        180000: "metrics_buffer_allocation_rate_pg10_plus",
    },
    "metrics.restartpoint_events": {
        170000: "metrics_restartpoint_events_pg17_plus",
        180000: "metrics_restartpoint_events_pg17_plus",
    },
}

EPOCH_REFS = {
    "buffer_writes_by_process": [
        "dimensions.bgwriter_stats_reset",
        "dimensions.checkpointer_stats_reset",
        "dimensions.io_stats_reset",
    ],
    "writer_pressure_events": [
        "dimensions.bgwriter_stats_reset",
        "dimensions.io_stats_reset",
    ],
}

T0 = "2026-09-04T10:00:00+00:00"
T1 = "2026-09-04T10:00:10+00:00"
T2 = "2026-09-04T10:00:20+00:00"
RESET = "2026-09-01T00:00:00+00:00"


def _semantics(content, source_id: str, version: int) -> dict[str, dict[str, str]]:
    source = content.queries[source_id]
    selected = select_query_variant(source_id, source, version)
    assert selected.status == "ok", (source_id, version)
    return selected.variant["semantic_columns"]


def _samples(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [{"timestamp": timestamp, "rows": [row]} for timestamp, row in zip((T0, T1, T2), rows)]


def _points(result: dict, name: str) -> list[object]:
    series = {entry["name"]: entry for entry in result["series"]}
    return [point["value"] for point in series[name]["points"]]


def test_checkpoint_charts_follow_io_read_write_rate(content_path: Path) -> None:
    content = load_content(content_path)
    section = content.report["sections"]["snapshot_charts_db"]["items"]
    keys = list(section)
    start = keys.index("io_read_write_rate") + 1
    assert tuple(keys[start : start + len(CHARTS)]) == tuple(CHARTS)
    for key, (metric_id, _source, _kind, _unit, _series) in CHARTS.items():
        item = section[key]
        assert item["metric"] == metric_id
        assert item["state"] == "collapsed", key
        assert "Checkpoints" in item["tags"], key


def test_checkpoint_chart_metrics_declare_the_snapshot_contract(content_path: Path) -> None:
    content = load_content(content_path)
    for key, (metric_id, source_id, kind, unit, expected_series) in CHARTS.items():
        metric = content.metrics[metric_id]
        assert metric["source_query"] == source_id, key
        assert metric["requires_collection"] == "every_snapshot", key
        assert metric["epoch_refs"] == EPOCH_REFS.get(key, ["dimensions.stats_reset"]), key
        assert metric["database_scope"] == "all_databases", key
        assert metric["chart"] == {"kind": kind, "unit": unit}, key
        declared = {
            series["name"]: (
                series["transform"],
                series["unit"],
                series.get("quantity"),
                series.get("optional", False),
            )
            for series in metric["series"]
        }
        assert declared == expected_series, key
        source = content.queries[source_id]
        assert source["collection"]["default"] == "every_snapshot", source_id
        assert source["database_scope"] == "all_databases", source_id


def test_each_checkpoint_chart_owns_its_source(content_path: Path) -> None:
    # Isolation: a chart source feeds exactly one item, and no chart borrows the
    # window-endpoint sources that belong to the delta tables.
    content = load_content(content_path)
    owners: dict[str, list[str]] = {}
    for metric_id, metric in content.metrics.items():
        source_id = metric.get("source_query")
        if source_id:
            owners.setdefault(source_id, []).append(metric_id)
    for metric_id, source_id, *_rest in CHARTS.values():
        assert owners[source_id] == [metric_id], source_id
    assert owners["metrics.checkpointer_delta"] == ["checkpoints.checkpointer_delta"]
    assert owners["metrics.bgwriter_delta"] == ["checkpoints.bgwriter_delta"]


def test_checkpoint_chart_sources_resolve_one_variant_per_major(content_path: Path) -> None:
    content = load_content(content_path)
    for source_id, expected in VARIANTS.items():
        source = content.queries[source_id]
        for version, variant_id in expected.items():
            selection = select_query_variant(source_id, source, version)
            assert selection.status == "ok", (source_id, version)
            assert selection.variant["id"] == variant_id, (source_id, version)

    restartpoints = content.queries["metrics.restartpoint_events"]
    for version in (100000, 160000):
        selection = select_query_variant("metrics.restartpoint_events", restartpoints, version)
        assert selection.status == "unsupported", version
        assert "PostgreSQL 17" in str(selection.reason)


def test_checkpoint_chart_sql_returns_raw_cluster_counters(content_path: Path) -> None:
    content = load_content(content_path)
    for _key, (_metric_id, source_id, *_rest) in CHARTS.items():
        for variant in content.queries[source_id]["variants"]:
            sql_file = variant["sql_file"]
            sql = (content.path / "queries" / sql_file).read_text(encoding="utf-8")
            assert lint_sql(sql) == [], sql_file
            assert "statement_timestamp() as snapshot_time" in sql, sql_file
            assert "'cluster'::text as scope" in sql, sql_file
            assert "stats_reset" in sql, sql_file
            # Endpoint SQL returns counters; the engine computes every delta and rate.
            assert "extract(epoch" not in sql, sql_file
            assert " / " not in sql, sql_file
            semantics = variant["semantic_columns"]
            for column in (*semantics["dimensions"].values(), *semantics["counters"].values()):
                assert f" {column}" in sql or f".{column}" in sql, (sql_file, column)
            if source_id == "metrics.buffer_writes_by_process":
                assert "current_setting('block_size')" in sql, sql_file
                if variant["id"] == "metrics_buffer_writes_by_process_pg17":
                    assert "coalesce(extends, 0)" in sql, sql_file
                    assert "op_bytes" in sql, sql_file
                if variant["id"] == "metrics_buffer_writes_by_process_pg18_plus":
                    assert "coalesce(extend_bytes, 0)" in sql, sql_file
            if "pg_stat_io" in sql:
                assert "object = 'relation'" in sql, sql_file
                if source_id == "metrics.writer_pressure_events":
                    assert "context = 'normal'" in sql, sql_file
                    assert "backend_type <> 'checkpointer'" in sql, sql_file
                else:
                    assert "not in ('checkpointer', 'background writer')" in sql, sql_file


def test_trigger_chart_reports_counter_deltas_per_interval(content_path: Path) -> None:
    content = load_content(content_path)
    metric = content.metrics["checkpoints.trigger_events"]
    semantics = _semantics(content, "metrics.checkpoint_trigger_events", 170000)
    samples = _samples(
        [
            {
                "scope": "cluster",
                "stats_reset": RESET,
                "checkpoints_timed": 10,
                "checkpoints_requested": 5,
                "checkpoints_completed": None,
            },
            {
                "scope": "cluster",
                "stats_reset": RESET,
                "checkpoints_timed": 11,
                "checkpoints_requested": 5,
                "checkpoints_completed": None,
            },
            {
                "scope": "cluster",
                "stats_reset": RESET,
                "checkpoints_timed": 11,
                "checkpoints_requested": 6,
                "checkpoints_completed": None,
            },
        ]
    )

    result = build_chart_result(metric, samples, semantics)

    # PostgreSQL 17 has no num_done: the optional series disappears instead of
    # being drawn as zeroes, and the remaining deltas stay exact integers.
    assert [series["name"] for series in result["series"]] == ["requested", "timed"]
    assert _points(result, "timed") == [None, 1, 0]
    assert _points(result, "requested") == [None, 0, 1]
    assert all(isinstance(value, int) for value in _points(result, "timed")[1:])


def test_declared_series_quantity_reaches_the_resolved_descriptor(content_path: Path) -> None:
    content = load_content(content_path)
    metric = content.metrics["checkpoints.trigger_events"]
    semantics = _semantics(content, "metrics.checkpoint_trigger_events", 180000)
    samples = _samples(
        [
            {
                "scope": "cluster",
                "stats_reset": RESET,
                "checkpoints_timed": 10,
                "checkpoints_requested": 5,
                "checkpoints_completed": 15,
            },
            {
                "scope": "cluster",
                "stats_reset": RESET,
                "checkpoints_timed": 11,
                "checkpoints_requested": 5,
                "checkpoints_completed": 16,
            },
        ]
    )
    artifact = {
        "items": {
            "snapshot_charts_db.checkpoint_trigger_events": {
                "source_kind": "metric",
                "source_metadata": {"metric_id": "checkpoints.trigger_events"},
                "result": build_chart_result(metric, samples, semantics),
            }
        },
        "snapshot_schemas": {},
        "snapshots": [],
    }

    apply_presentation_contract(content, artifact)

    result = artifact["items"]["snapshot_charts_db.checkpoint_trigger_events"]["result"]
    # The unit alone says "count"; the series names what is counted.
    assert {series["quantity"] for series in result["series"]} == {"events"}
    assert result["chart"]["quantity"] == "events"
    timed = next(series for series in result["series"] if series["name"] == "timed")
    assert timed["value_kind"] == "integer"
    assert timed["encoding"] == "decimal_string"
    assert timed["points"][1]["value"] == "1"


def test_trigger_chart_shows_completed_checkpoints_on_pg18(content_path: Path) -> None:
    content = load_content(content_path)
    metric = content.metrics["checkpoints.trigger_events"]
    semantics = _semantics(content, "metrics.checkpoint_trigger_events", 180000)
    samples = _samples(
        [
            {
                "scope": "cluster",
                "stats_reset": RESET,
                "checkpoints_timed": 10,
                "checkpoints_requested": 5,
                "checkpoints_completed": 12,
            },
            {
                "scope": "cluster",
                "stats_reset": RESET,
                "checkpoints_timed": 11,
                "checkpoints_requested": 5,
                "checkpoints_completed": 12,
            },
            {
                "scope": "cluster",
                "stats_reset": RESET,
                "checkpoints_timed": 12,
                "checkpoints_requested": 5,
                "checkpoints_completed": 13,
            },
        ]
    )

    result = build_chart_result(metric, samples, semantics)

    # A timed checkpoint was skipped in the first interval, so completed lags timed.
    assert _points(result, "timed") == [None, 1, 1]
    assert _points(result, "completed") == [None, 0, 1]


def test_trigger_source_marks_completed_as_unsupported_before_pg18(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    variants = content.queries["metrics.checkpoint_trigger_events"]["variants"]

    for variant in variants[:2]:
        status = variant["column_statuses"]["checkpoints_completed"]
        assert status["status"] == "unsupported"
        assert "idle skips" in status["reason"]
    assert "column_statuses" not in variants[2]


def test_trigger_chart_turns_a_statistics_reset_into_a_gap(content_path: Path) -> None:
    content = load_content(content_path)
    metric = content.metrics["checkpoints.trigger_events"]
    semantics = _semantics(content, "metrics.checkpoint_trigger_events", 160000)
    samples = _samples(
        [
            {
                "scope": "cluster",
                "stats_reset": RESET,
                "checkpoints_timed": 10,
                "checkpoints_requested": 5,
                "checkpoints_completed": None,
            },
            {
                "scope": "cluster",
                "stats_reset": RESET,
                "checkpoints_timed": 11,
                "checkpoints_requested": 5,
                "checkpoints_completed": None,
            },
            {
                "scope": "cluster",
                "stats_reset": T1,
                "checkpoints_timed": 1,
                "checkpoints_requested": 0,
                "checkpoints_completed": None,
            },
        ]
    )

    result = build_chart_result(metric, samples, semantics)

    assert _points(result, "timed") == [None, 1, None]
    assert result["interval_coverage"]["counts"]["epoch_changed"] >= 1


def test_buffer_writes_chart_reports_bytes_per_second_per_writer(content_path: Path) -> None:
    content = load_content(content_path)
    metric = content.metrics["checkpoints.buffer_writes_by_process"]
    semantics = _semantics(content, "metrics.buffer_writes_by_process", 160000)
    samples = _samples(
        [
            {
                "scope": "cluster",
                "bgwriter_stats_reset": RESET,
                "checkpointer_stats_reset": RESET,
                "io_stats_reset": RESET,
                "checkpointer_bytes": 0,
                "bgwriter_bytes": 8192,
                "backend_bytes": 0,
            },
            {
                "scope": "cluster",
                "bgwriter_stats_reset": RESET,
                "checkpointer_stats_reset": RESET,
                "io_stats_reset": RESET,
                "checkpointer_bytes": 81920,
                "bgwriter_bytes": 16384,
                "backend_bytes": 0,
            },
            {
                "scope": "cluster",
                "bgwriter_stats_reset": RESET,
                "checkpointer_stats_reset": RESET,
                "io_stats_reset": RESET,
                "checkpointer_bytes": 163840,
                "bgwriter_bytes": 8192,
                "backend_bytes": 0,
            },
        ]
    )

    result = build_chart_result(metric, samples, semantics)

    # Backends never wrote: the all-zero series is omitted rather than stacked
    # as a flat zero band. A decrease in one counter blanks only that series.
    assert [series["name"] for series in result["series"]] == [
        "background writer",
        "checkpointer",
    ]
    assert _points(result, "checkpointer") == [None, 8192.0, 8192.0]
    assert _points(result, "background writer") == [None, 819.2, None]
    assert result["interval_coverage"]["counts"]["counter_decrease"] == 1


def test_buffer_writes_chart_rejects_each_independent_pg17_epoch(content_path: Path) -> None:
    content = load_content(content_path)
    metric = content.metrics["checkpoints.buffer_writes_by_process"]
    semantics = _semantics(content, "metrics.buffer_writes_by_process", 170000)

    for changed_epoch in (
        "bgwriter_stats_reset",
        "checkpointer_stats_reset",
        "io_stats_reset",
    ):
        rows = [
            {
                "scope": "cluster",
                "bgwriter_stats_reset": RESET,
                "checkpointer_stats_reset": RESET,
                "io_stats_reset": RESET,
                "checkpointer_bytes": 0,
                "bgwriter_bytes": 0,
                "backend_bytes": 0,
            },
            {
                "scope": "cluster",
                "bgwriter_stats_reset": RESET,
                "checkpointer_stats_reset": RESET,
                "io_stats_reset": RESET,
                "checkpointer_bytes": 100,
                "bgwriter_bytes": 100,
                "backend_bytes": 100,
            },
            {
                "scope": "cluster",
                "bgwriter_stats_reset": RESET,
                "checkpointer_stats_reset": RESET,
                "io_stats_reset": RESET,
                "checkpointer_bytes": 200,
                "bgwriter_bytes": 200,
                "backend_bytes": 200,
            },
        ]
        rows[2][changed_epoch] = T2

        result = build_chart_result(metric, _samples(rows), semantics)

        assert _points(result, "checkpointer") == [None, 10.0, None], changed_epoch
        assert _points(result, "background writer") == [None, 10.0, None], changed_epoch
        assert _points(result, "backends") == [None, 10.0, None], changed_epoch
        assert result["interval_coverage"]["counts"]["epoch_changed"] == 3


def test_writer_pressure_chart_rejects_each_independent_pg17_epoch(content_path: Path) -> None:
    content = load_content(content_path)
    metric = content.metrics["checkpoints.writer_pressure_events"]
    semantics = _semantics(content, "metrics.writer_pressure_events", 170000)

    for changed_epoch in ("bgwriter_stats_reset", "io_stats_reset"):
        rows = [
            {
                "scope": "cluster",
                "bgwriter_stats_reset": RESET,
                "io_stats_reset": RESET,
                "bgwriter_stops": 0,
                "backend_fsyncs": 0,
            },
            {
                "scope": "cluster",
                "bgwriter_stats_reset": RESET,
                "io_stats_reset": RESET,
                "bgwriter_stops": 1,
                "backend_fsyncs": 1,
            },
            {
                "scope": "cluster",
                "bgwriter_stats_reset": RESET,
                "io_stats_reset": RESET,
                "bgwriter_stops": 2,
                "backend_fsyncs": 2,
            },
        ]
        rows[2][changed_epoch] = T2

        result = build_chart_result(metric, _samples(rows), semantics)

        assert _points(result, "bgwriter stops") == [None, 1, None], changed_epoch
        assert _points(result, "backend fsyncs") == [None, 1, None], changed_epoch
        assert result["interval_coverage"]["counts"]["epoch_changed"] == 2


def test_write_sync_chart_reports_phase_time_published_in_milliseconds(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    metric = content.metrics["checkpoints.write_sync_time_delta"]
    semantics = _semantics(content, "metrics.checkpoint_write_sync_time", 180000)
    samples = _samples(
        [
            {"scope": "cluster", "stats_reset": RESET, "write_time_ms": 100.5, "sync_time_ms": 0},
            {"scope": "cluster", "stats_reset": RESET, "write_time_ms": 1100.5, "sync_time_ms": 25},
            {"scope": "cluster", "stats_reset": RESET, "write_time_ms": 1100.5, "sync_time_ms": 25},
        ]
    )

    result = build_chart_result(metric, samples, semantics)

    assert _points(result, "write") == [None, 1000.0, 0.0]
    assert _points(result, "sync") == [None, 25.0, 0.0]


def test_restartpoint_chart_is_empty_on_a_primary(content_path: Path) -> None:
    content = load_content(content_path)
    metric = content.metrics["checkpoints.restartpoint_events"]
    semantics = _semantics(content, "metrics.restartpoint_events", 170000)
    zero = {
        "scope": "cluster",
        "stats_reset": RESET,
        "restartpoints_timed": 0,
        "restartpoints_requested": 0,
        "restartpoints_done": 0,
    }

    result = build_chart_result(metric, _samples([dict(zero), dict(zero), dict(zero)]), semantics)

    assert result["series"] == []


def test_checkpoint_chart_instructions_point_at_the_window_totals(content_path: Path) -> None:
    content = load_content(content_path)
    for key in CHARTS:
        text = content.instructions[f"snapshot_charts_db.{key}"]["text"]
        assert f"report item `snapshot_charts_db.{key}`" in text, key
        for heading in (
            "## What this item shows",
            "## What to watch",
            "## Common fault causes",
            "## Automatic evaluation",
            "## Related report items",
            "## Checklist",
        ):
            assert text.count(heading) == 1, (key, heading)
        assert "#item-snapshot_delta_workload." in text, key


def test_checkpoint_chart_instructions_do_not_claim_snapshot_phase_timing(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    phase_text = content.instructions["snapshot_charts_db.checkpoint_write_sync_time_delta"]["text"]
    trigger_text = content.instructions["snapshot_charts_db.checkpoint_trigger_events"]["text"]
    buffer_text = content.instructions["snapshot_charts_db.buffer_writes_by_process"]["text"]
    restartpoint_text = content.instructions["snapshot_charts_db.restartpoint_events"]["text"]
    delta_text = content.instructions["snapshot_delta_workload.checkpointer_delta"]["text"]

    assert "27,000 ms delta" in phase_text
    assert "not \"this much work occurred during this interval\"" in phase_text
    assert "every supported PostgreSQL version" in phase_text
    assert "publication buckets" in trigger_text
    assert "different interval columns" in trigger_text
    assert "requests were coalesced" not in trigger_text
    assert "more than one in five" not in trigger_text
    assert "writes + extends" in buffer_text
    assert "not directly comparable" in buffer_text
    assert "published incrementally" in buffer_text
    assert "standby's `max_wal_size`" in restartpoint_text
    assert "do not imply a manual or explicit user request" in restartpoint_text
    assert "available only on PostgreSQL 18 and newer" in delta_text
    assert "restartpoints on every supported PostgreSQL version" in delta_text
