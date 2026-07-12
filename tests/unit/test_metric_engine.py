from __future__ import annotations

from pathlib import Path

from pg_diag.content_loader import load_content
from pg_diag.metric_engine import (
    _metric_source_text,
    build_chart_result,
    build_metric_item,
    build_table_result,
    evaluate_metric_table_findings,
)
from pg_diag.planner import PlannedItem
from pg_diag.versioning import select_query_variant


NEW_DELTA_METRICS = {
    "statements.temp_io_delta",
    "io.activity_delta",
    "checkpoints.checkpointer_delta",
    "wal.activity_delta",
    "objects.table_maintenance_delta",
    "replication.recovery_conflicts_delta",
    "database.session_outcomes_delta",
    "replication.physical_progress_delta",
    "statements.planning_delta",
    "checkpoints.bgwriter_delta",
    "slru.activity_delta",
    "wal.archiver_delta",
    "replication.logical_slot_delta",
    "replication.subscription_errors_delta",
}


def test_new_delta_metric_contracts_resolve_all_columns(content_path: Path) -> None:
    content = load_content(content_path)

    for metric_id in sorted(NEW_DELTA_METRICS):
        metric = content.metrics[metric_id]
        source = content.queries[metric["source_query"]]
        selected = select_query_variant(source["title"], source, 180000)
        semantics = selected.variant.get("semantic_columns") or {}
        first_row = {"snapshot_time": "2026-07-12T00:00:00+00:00"}
        last_row = {"snapshot_time": "2026-07-12T00:00:10+00:00"}

        for semantic_name, column_name in (semantics.get("dimensions") or {}).items():
            value = "2026-07-01T00:00:00+00:00" if "reset" in semantic_name or "start" in semantic_name else f"{semantic_name}-1"
            first_row[column_name] = value
            last_row[column_name] = value
        for column_name in (semantics.get("counters") or {}).values():
            first_row[column_name] = 10
            last_row[column_name] = 20

        result = build_table_result(
            metric,
            [
                {"timestamp": first_row["snapshot_time"], "rows": [first_row]},
                {"timestamp": last_row["snapshot_time"], "rows": [last_row]},
            ],
            semantics,
        )

        assert result["row_count"] == 1, metric_id
        assert result["delta_window"]["duration_seconds"] == 10.0, metric_id
        assert [column["name"] for column in result["columns"]] == [
            column["name"] for column in metric["table"]["columns"]
        ], metric_id


def test_delta_table_metric_uses_first_and_last_samples() -> None:
    metric = {
        "table": {
            "key_refs": ["dimensions.database"],
            "sort": {"column": "commits_per_sec", "direction": "desc"},
            "columns": [
                {"name": "datname", "role": "key", "key_index": 0},
                {"name": "commit_delta", "value_ref": "counters.xact_commit", "transform": "delta"},
                {"name": "commits_per_sec", "value_ref": "counters.xact_commit", "transform": "rate"},
            ],
        }
    }
    semantic_columns = {
        "dimensions": {"database": "datname"},
        "counters": {"xact_commit": "xact_commit"},
    }
    samples = [
        {"timestamp": "2026-07-05T00:00:00+00:00", "rows": [{"datname": "db", "xact_commit": 10}]},
        {"timestamp": "2026-07-05T00:00:05+00:00", "rows": [{"datname": "db", "xact_commit": 30}]},
    ]

    result = build_table_result(metric, samples, semantic_columns)

    assert result["rows"] == [["db", 20.0, 4.0]]


def test_delta_table_rejects_changed_counter_epoch_even_when_counter_increases() -> None:
    metric = {
        "table": {
            "key_refs": ["dimensions.database_id"],
            "epoch_refs": ["dimensions.stats_reset"],
            "columns": [
                {"name": "datid", "role": "key", "key_index": 0},
                {"name": "delta", "value_ref": "counters.value", "transform": "delta"},
            ],
        }
    }
    semantics = {
        "dimensions": {"database_id": "datid", "stats_reset": "stats_reset"},
        "counters": {"value": "value"},
    }
    samples = [
        {
            "timestamp": "2026-07-05T00:00:00+00:00",
            "rows": [{"datid": 1, "stats_reset": "2026-07-01", "value": 10}],
        },
        {
            "timestamp": "2026-07-05T00:00:05+00:00",
            "rows": [{"datid": 1, "stats_reset": "2026-07-05", "value": 50}],
        },
    ]

    result = build_table_result(metric, samples, semantics)

    assert result["rows"] == []
    assert result["interval_coverage"]["invalid"] == 1
    assert result["interval_coverage"]["counts"] == {"epoch_changed": 1}


def test_delta_table_reports_raw_database_counter_delta_and_rate() -> None:
    metric = {
        "table": {
            "key_refs": ["database"],
            "columns": [
                {"name": "database", "role": "key", "key_index": 0},
                {"name": "delta", "value_ref": "commits", "transform": "delta"},
                {"name": "rate", "value_ref": "commits", "transform": "rate"},
            ],
        }
    }
    samples = [
        {"timestamp": "2026-07-05T00:00:00+00:00", "rows": [{"database": "db", "commits": 10}]},
        {"timestamp": "2026-07-05T00:00:05+00:00", "rows": [{"database": "db", "commits": 20}]},
    ]

    result = build_table_result(metric, samples, {})

    assert result["rows"] == [["db", 10.0, 2.0]]


def test_delta_table_preserves_exact_integer_beyond_json_safe_range() -> None:
    metric = {
        "table": {
            "key_refs": ["name"],
            "columns": [
                {"name": "name", "role": "key", "key_index": 0},
                {"name": "value_delta", "value_ref": "value", "transform": "delta"},
            ],
        }
    }
    samples = [
        {"timestamp": "2026-07-05T00:00:00+00:00", "rows": [{"name": "x", "value": 9007199254740993}]},
        {"timestamp": "2026-07-05T00:00:05+00:00", "rows": [{"name": "x", "value": 9007199254740995}]},
    ]

    result = build_table_result(metric, samples, {})

    assert result["rows"] == [["x", 2]]


def test_delta_table_propagates_optional_source_column_status() -> None:
    metric = {
        "table": {
            "drop_zero_rows": False,
            "key_refs": ["dimensions.subscription_id"],
            "columns": [
                {"name": "subid", "role": "key", "key_index": 0},
                {"name": "apply_delta", "value_ref": "counters.apply", "transform": "delta"},
                {"name": "conflict_delta", "value_ref": "counters.conflict", "transform": "delta"},
            ],
        }
    }
    semantics = {
        "dimensions": {"subscription_id": "subid"},
        "counters": {"apply": "apply_count", "conflict": "conflict_count"},
    }
    samples = [
        {"timestamp": "2026-07-05T00:00:00+00:00", "rows": [{"subid": 1, "apply_count": 10, "conflict_count": None}]},
        {"timestamp": "2026-07-05T00:00:05+00:00", "rows": [{"subid": 1, "apply_count": 12, "conflict_count": None}]},
    ]
    status = {
        "conflict_count": {
            "status": "unsupported",
            "reason": "Conflict counters are available from PostgreSQL 18",
        }
    }

    result = build_table_result(metric, samples, semantics, status)

    assert result["rows"] == [[1, 2, None]]
    assert result["column_statuses"] == {
        "conflict_delta": status["conflict_count"]
    }
    assert result["interval_coverage"]["counts"] == {"ok": 1}


def test_delta_table_keeps_row_when_optional_counter_is_null() -> None:
    metric = {
        "table": {
            "key_refs": ["name"],
            "columns": [
                {"name": "name", "role": "key", "key_index": 0},
                {
                    "name": "optional_delta",
                    "value_ref": "optional_value",
                    "transform": "delta",
                    "optional": True,
                },
                {"name": "required_delta", "value_ref": "required_value", "transform": "delta"},
            ],
        }
    }
    samples = [
        {
            "timestamp": "2026-07-05T00:00:00+00:00",
            "rows": [{"name": "x", "optional_value": None, "required_value": 10}],
        },
        {
            "timestamp": "2026-07-05T00:00:05+00:00",
            "rows": [{"name": "x", "optional_value": None, "required_value": 12}],
        },
    ]

    result = build_table_result(metric, samples, {})

    assert result["rows"] == [["x", None, 2]]
    assert result["interval_coverage"]["counts"] == {"ok": 1}


def test_chart_rate_uses_raw_database_counter_delta() -> None:
    metric = {
        "partition_by": ["dimensions.database"],
        "series": [
            {
                "name": "commits",
                "value_ref": "counters.xact_commit",
                "transform": "rate",
                "unit": "tx/s",
            }
        ],
        "chart": {"kind": "area", "unit": "tx/s"},
    }
    semantics = {
        "dimensions": {"database": "datname"},
        "counters": {"xact_commit": "xact_commit"},
    }
    samples = [
        {"timestamp": "2026-07-05T00:00:00+00:00", "rows": [{"datname": "db", "xact_commit": 10}]},
        {"timestamp": "2026-07-05T00:00:05+00:00", "rows": [{"datname": "db", "xact_commit": 16}]},
        {"timestamp": "2026-07-05T00:00:10+00:00", "rows": [{"datname": "db", "xact_commit": 17}]},
    ]

    result = build_chart_result(metric, samples, semantics)

    assert result["series"][0]["points"] == [
        {"t": "2026-07-05T00:00:00+00:00", "value": None},
        {"t": "2026-07-05T00:00:05+00:00", "value": 1.2},
        {"t": "2026-07-05T00:00:10+00:00", "value": 0.2},
    ]


def test_metric_table_evaluation_builds_summary_for_matching_rows() -> None:
    result = {
        "kind": "table",
        "columns": [{"name": "seq_scans_per_sec"}, {"name": "seq_tup_read_per_sec"}],
        "rows": [[12.0, 15000.0], [1.0, 100.0]],
    }
    evaluation = {
        "summary_title": "Sequential scans require review",
        "recommendation": "Inspect representative plans.",
        "rules": [
            {
                "severity": "medium",
                "reason": "Sustained sequential scans",
                "all": [
                    {"column": "seq_scans_per_sec", "operator": "gte", "value": 10},
                    {"column": "seq_tup_read_per_sec", "operator": "gte", "value": 10000},
                ],
            }
        ],
    }

    severity, issues = evaluate_metric_table_findings(result, evaluation)

    assert severity == "medium"
    assert issues["summary"]["title"] == "Sequential scans require review"
    assert "Sustained sequential scans" in issues["summary"]["description"]


def test_window_endpoint_metric_source_header_names_endpoint_collection() -> None:
    source = _metric_source_text(
        {
            "title": "SQL WAL Delta",
            "source_query": "metrics.statements_wal_delta",
            "requires_collection": "window_endpoints",
            "table": {"mode": "first_last_delta", "limit": 50},
        },
        "select 1",
        "sql",
    )

    assert "-- requires_collection: window_endpoints" in source
    assert "-- window endpoint source follows" in source
    assert "sampled SQL source follows" not in source


def test_delta_table_metric_uses_row_snapshot_time_for_rate_interval() -> None:
    metric = {
        "table": {
            "key_refs": ["dimensions.database"],
            "columns": [
                {"name": "datname", "role": "key", "key_index": 0},
                {"name": "commits_per_sec", "value_ref": "counters.xact_commit", "transform": "rate"},
            ],
        }
    }
    semantic_columns = {
        "dimensions": {"database": "datname"},
        "counters": {"xact_commit": "xact_commit"},
    }
    samples = [
        {
            "timestamp": "2026-07-05T00:00:00+00:00",
            "rows": [{"snapshot_time": "2026-07-05T00:00:05+00:00", "datname": "db", "xact_commit": 10}],
        },
        {
            "timestamp": "2026-07-05T00:00:05+00:00",
            "rows": [{"snapshot_time": "2026-07-05T00:00:15+00:00", "datname": "db", "xact_commit": 30}],
        },
    ]

    result = build_table_result(metric, samples, semantic_columns)

    assert result["rows"] == [["db", 2.0]]


def test_delta_table_omits_unknown_deltas_and_reports_compact_coverage() -> None:
    metric = {
        "table": {
            "key_refs": ["name"],
            "columns": [
                {"name": "name", "role": "key", "key_index": 0},
                {"name": "delta", "value_ref": "counter", "transform": "delta"},
            ],
        }
    }
    samples = [
        {
            "timestamp": "2026-07-05T00:00:00+00:00",
            "rows": [
                {"name": "valid", "counter": 10},
                {"name": "decreased", "counter": 100},
                {"name": "left_limit", "counter": 5},
            ],
        },
        {
            "timestamp": "2026-07-05T00:00:05+00:00",
            "rows": [
                {"name": "valid", "counter": 30},
                {"name": "decreased", "counter": 1},
                {"name": "entered_limit", "counter": 7},
            ],
        },
    ]

    result = build_table_result(metric, samples, {})

    assert result["rows"] == [["valid", 20.0]]
    assert result["interval_coverage"] == {
        "total": 4,
        "comparable": 1,
        "unmatched": 2,
        "invalid": 1,
        "counts": {
            "ok": 1,
            "missing_start": 1,
            "missing_end": 1,
            "counter_decrease": 1,
        },
    }
    assert result["delta_window"] == {
        "start_time": "2026-07-05T00:00:00+00:00",
        "finish_time": "2026-07-05T00:00:05+00:00",
        "duration_seconds": 5.0,
    }


def test_sample_sum_table_metric_aggregates_all_samples() -> None:
    metric = {
        "table": {
            "mode": "sample_sum",
            "key_refs": ["wait_event"],
            "sort": {"column": "sampled_session_points", "direction": "desc"},
            "columns": [
                {"name": "wait_event", "role": "key", "key_index": 0},
                {"name": "samples_seen", "transform": "sample_count"},
                {"name": "sampled_session_points", "value_ref": "sessions", "transform": "sum"},
                {"name": "max_sessions", "value_ref": "sessions", "transform": "max"},
            ],
        }
    }
    samples = [
        {"timestamp": "2026-07-05T00:00:00+00:00", "rows": [{"wait_event": "CPU", "sessions": 2}]},
        {"timestamp": "2026-07-05T00:00:05+00:00", "rows": [{"wait_event": "CPU", "sessions": 3}]},
    ]

    result = build_table_result(metric, samples, {})

    assert result["rows"] == [["CPU", 2, 5.0, 3.0]]


def test_sample_sum_table_preserves_unknown_aggregates_as_null() -> None:
    metric = {
        "table": {
            "mode": "sample_sum",
            "key_refs": ["pid"],
            "drop_zero_rows": False,
            "columns": [
                {"name": "pid", "role": "key", "key_index": 0},
                {"name": "io_access", "ref": "io_access", "transform": "last"},
                {"name": "avg_read", "value_ref": "read", "transform": "avg"},
                {"name": "sum_read", "value_ref": "read", "transform": "sum"},
                {"name": "max_read", "value_ref": "read", "transform": "max"},
            ],
        }
    }
    samples = [
        {
            "timestamp": "2026-07-05T00:00:00+00:00",
            "rows": [{"pid": 101, "io_access": False, "read": None}],
        }
    ]

    result = build_table_result(metric, samples, {})

    assert result["rows"] == [[101, False, None, None, None]]


def test_top_n_interval_chart_joins_adjacent_snapshots_in_memory() -> None:
    metric = {
        "chart": {"kind": "stacked_column", "unit": "rows/s"},
        "top_n": {
            "mode": "interval",
            "limit": 1,
            "key_refs": ["schema", "table"],
            "label_refs": ["schema", "table"],
            "value_refs": ["inserts", "updates"],
            "transform": "rate",
            "unit": "rows/s",
        },
    }
    samples = [
        {
            "timestamp": "2026-07-05T00:00:00+00:00",
            "rows": [
                {"schema": "public", "table": "small", "inserts": 10, "updates": 10},
                {"schema": "public", "table": "hot", "inserts": 100, "updates": 100},
            ],
        },
        {
            "timestamp": "2026-07-05T00:00:05+00:00",
            "rows": [
                {"schema": "public", "table": "small", "inserts": 15, "updates": 15},
                {"schema": "public", "table": "hot", "inserts": 160, "updates": 140},
            ],
        },
    ]

    result = build_chart_result(metric, samples, {})

    assert result["chart"]["kind"] == "stacked_column"
    assert result["series"] == [
        {
            "name": "public.hot",
            "unit": "rows/s",
            "points": [{"t": "2026-07-05T00:00:05+00:00", "value": 20.0}],
        }
    ]


def test_top_n_interval_allows_different_limited_row_sets() -> None:
    metric = {
        "chart": {"kind": "stacked_column", "unit": "rows/s"},
        "top_n": {
            "mode": "interval",
            "limit": 10,
            "key_refs": ["table"],
            "label_refs": ["table"],
            "value_ref": "inserts",
            "transform": "rate",
            "unit": "rows/s",
        },
    }
    samples = [
        {
            "timestamp": "2026-07-05T00:00:00+00:00",
            "rows": [
                {"table": "left_limit", "inserts": 10},
                {"table": "shared", "inserts": 20},
            ],
        },
        {
            "timestamp": "2026-07-05T00:00:05+00:00",
            "rows": [
                {"table": "shared", "inserts": 30},
                {"table": "entered_limit", "inserts": 40},
            ],
        },
    ]

    result = build_chart_result(metric, samples, {})

    assert result["series"] == [
        {
            "name": "shared",
            "unit": "rows/s",
            "points": [{"t": "2026-07-05T00:00:05+00:00", "value": 2.0}],
        }
    ]
    assert result["interval_coverage"] == {
        "total": 3,
        "comparable": 1,
        "unmatched": 2,
        "invalid": 0,
        "counts": {"ok": 1, "missing_start": 1, "missing_end": 1},
    }


def test_metric_item_warns_for_invalid_delta_but_not_limited_row_churn() -> None:
    planned = PlannedItem(
        item_id="snapshot_charts_db.tables_top_insert_rate",
        section_id="snapshot_charts_db",
        item_key="tables_top_insert_rate",
        title="Top Tables By Insert Rate",
        source_kind="metric",
        status="planned",
        source_id="objects.tables_top_insert_rate",
    )
    metric = {
        "title": "Top Tables By Insert Rate",
        "source_query": "metrics.objects_tables_top_insert_rate",
        "requires_collection": "every_snapshot",
        "chart": {"kind": "stacked_column", "unit": "rows/s"},
        "top_n": {
            "mode": "interval",
            "limit": 10,
            "key_refs": ["table"],
            "label_refs": ["table"],
            "value_ref": "inserts",
            "transform": "rate",
        },
    }
    source_item_id = "__metric_sources.tables_top_insert_rate"

    def snapshot(timestamp: str, rows: list[list[object]]) -> dict:
        return {
            "timestamp": timestamp,
            "items": {
                source_item_id: {
                    "collection_status": "ok",
                    "result": {
                        "kind": "table",
                        "columns": [{"name": "table"}, {"name": "inserts"}],
                        "rows": rows,
                    },
                }
            },
        }

    common_args = {
        "planned": planned,
        "metric": metric,
        "sampler_samples": {},
        "source_item_by_query": {metric["source_query"]: source_item_id},
        "source_metadata_by_item": {
            source_item_id: {"source_text": "select limited counters", "source_language": "sql"}
        },
    }
    churn_item = build_metric_item(
        db_snapshots=[
            snapshot("2026-07-05T00:00:00+00:00", [["left", 10], ["shared", 20]]),
            snapshot("2026-07-05T00:00:05+00:00", [["shared", 30], ["entered", 40]]),
        ],
        **common_args,
    )

    assert churn_item["collection_status"] == "ok"
    assert churn_item["reason"] is None
    assert churn_item["diagnostics"] == []
    assert churn_item["result"]["interval_coverage"]["unmatched"] == 2

    invalid_item = build_metric_item(
        db_snapshots=[
            snapshot("2026-07-05T00:00:00+00:00", [["shared", 100]]),
            snapshot("2026-07-05T00:00:05+00:00", [["shared", 1]]),
        ],
        **common_args,
    )

    assert invalid_item["collection_status"] == "empty"
    assert "could not be calculated" in invalid_item["reason"]
    assert invalid_item["diagnostics"][0]["code"] == "metric_interval_coverage"


def test_stacked_column_top_n_orders_largest_series_for_top_stack_position() -> None:
    metric = {
        "chart": {"kind": "stacked_column", "unit": "rows/s"},
        "top_n": {
            "mode": "interval",
            "limit": 2,
            "key_refs": ["schema", "table"],
            "label_refs": ["schema", "table"],
            "value_ref": "inserts",
            "transform": "rate",
            "unit": "rows/s",
        },
    }
    samples = [
        {
            "timestamp": "2026-07-05T00:00:00+00:00",
            "rows": [
                {"schema": "public", "table": "small", "inserts": 10},
                {"schema": "public", "table": "hot", "inserts": 100},
            ],
        },
        {
            "timestamp": "2026-07-05T00:00:05+00:00",
            "rows": [
                {"schema": "public", "table": "small", "inserts": 15},
                {"schema": "public", "table": "hot", "inserts": 160},
            ],
        },
    ]

    result = build_chart_result(metric, samples, {})

    assert [series["name"] for series in result["series"]] == ["public.small", "public.hot"]
    assert [series["points"][0]["value"] for series in result["series"]] == [1.0, 12.0]


def test_top_n_interval_uses_row_snapshot_time_for_point_and_rate_interval() -> None:
    metric = {
        "chart": {"kind": "stacked_column", "unit": "rows/s"},
        "top_n": {
            "mode": "interval",
            "limit": 1,
            "key_refs": ["table"],
            "label_refs": ["table"],
            "value_ref": "inserts",
            "transform": "rate",
            "unit": "rows/s",
        },
    }
    samples = [
        {
            "timestamp": "2026-07-05T00:00:00+00:00",
            "rows": [
                {"snapshot_time": "2026-07-05T00:00:00+00:00", "table": "cold", "inserts": 1},
                {"snapshot_time": "2026-07-05T00:00:05+00:00", "table": "hot", "inserts": 100},
            ],
        },
        {
            "timestamp": "2026-07-05T00:00:05+00:00",
            "rows": [
                {"snapshot_time": "2026-07-05T00:00:05+00:00", "table": "cold", "inserts": 2},
                {"snapshot_time": "2026-07-05T00:00:15+00:00", "table": "hot", "inserts": 200},
            ],
        },
    ]

    result = build_chart_result(metric, samples, {})

    assert result["series"] == [
        {
            "name": "hot",
            "unit": "rows/s",
            "points": [{"t": "2026-07-05T00:00:15+00:00", "value": 10.0}],
        }
    ]


def test_chart_prefers_row_snapshot_time_over_wrapper_time() -> None:
    metric = {
        "chart": {"kind": "line", "unit": "tx/s"},
        "series": [{"name": "commits", "value_ref": "xact_commit", "transform": "rate", "unit": "tx/s"}],
    }
    samples = [
        {
            "timestamp": "2026-07-05T00:00:00+00:00",
            "rows": [{"snapshot_time": "2026-07-05T00:00:01+00:00", "xact_commit": 10}],
        },
        {
            "timestamp": "2026-07-05T00:00:10+00:00",
            "rows": [{"snapshot_time": "2026-07-05T00:00:06+00:00", "xact_commit": 30}],
        },
    ]

    result = build_chart_result(metric, samples, {})

    assert result["series"] == [
        {
            "name": "commits",
            "unit": "tx/s",
            "color": None,
            "points": [
                {"t": "2026-07-05T00:00:01+00:00", "value": None},
                {"t": "2026-07-05T00:00:06+00:00", "value": 4.0},
            ],
        }
    ]


def test_chart_counter_decrease_is_a_gap_with_invalid_coverage() -> None:
    metric = {
        "chart": {"kind": "line", "unit": "tx/s"},
        "series": [
            {"name": "commits", "value_ref": "xact_commit", "transform": "rate"}
        ],
    }
    samples = [
        {"timestamp": "2026-07-05T00:00:00+00:00", "rows": [{"xact_commit": 100}]},
        {"timestamp": "2026-07-05T00:00:05+00:00", "rows": [{"xact_commit": 5}]},
    ]

    result = build_chart_result(metric, samples, {})

    assert result["series"][0]["points"][-1]["value"] is None
    assert result["interval_coverage"] == {
        "total": 1,
        "comparable": 0,
        "unmatched": 0,
        "invalid": 1,
        "counts": {"counter_decrease": 1},
    }


def test_top_n_first_last_ratio_chart_uses_counter_deltas() -> None:
    metric = {
        "chart": {"kind": "bar", "unit": "ratio"},
        "top_n": {
            "mode": "first_last",
            "operation": "ratio",
            "limit": 1,
            "key_refs": ["index"],
            "label_refs": ["index"],
            "numerator_refs": ["idx_tup_read"],
            "denominator_ref": "idx_scan",
            "series_name": "reads / scan",
            "unit": "ratio",
        },
    }
    samples = [
        {
            "timestamp": "2026-07-05T00:00:00+00:00",
            "rows": [
                {"snapshot_time": "2026-07-05T00:00:01+00:00", "index": "idx_a", "idx_tup_read": 100, "idx_scan": 10},
                {"snapshot_time": "2026-07-05T00:00:01+00:00", "index": "idx_b", "idx_tup_read": 100, "idx_scan": 10},
            ],
        },
        {
            "timestamp": "2026-07-05T00:00:10+00:00",
            "rows": [
                {"snapshot_time": "2026-07-05T00:00:06+00:00", "index": "idx_a", "idx_tup_read": 160, "idx_scan": 20},
                {"snapshot_time": "2026-07-05T00:00:06+00:00", "index": "idx_b", "idx_tup_read": 200, "idx_scan": 30},
            ],
        },
    ]

    result = build_chart_result(metric, samples, {})

    assert result["chart"]["x_type"] == "datetime"
    assert result["series"] == [
        {
            "name": "idx_a",
            "unit": "ratio",
            "points": [{"t": "2026-07-05T00:00:06+00:00", "value": 6.0}],
        }
    ]


def test_top_n_interval_ratio_chart_uses_snapshot_time_per_interval() -> None:
    metric = {
        "chart": {"kind": "stacked_column", "unit": "ratio"},
        "top_n": {
            "mode": "interval",
            "operation": "ratio",
            "limit": 1,
            "key_refs": ["index"],
            "label_refs": ["index"],
            "numerator_refs": ["idx_tup_read"],
            "denominator_ref": "idx_scan",
            "unit": "ratio",
        },
    }
    samples = [
        {
            "timestamp": "2026-07-05T00:00:00+00:00",
            "rows": [
                {"snapshot_time": "2026-07-05T00:00:01+00:00", "index": "idx_a", "idx_tup_read": 100, "idx_scan": 10},
                {"snapshot_time": "2026-07-05T00:00:01+00:00", "index": "idx_b", "idx_tup_read": 100, "idx_scan": 10},
            ],
        },
        {
            "timestamp": "2026-07-05T00:00:10+00:00",
            "rows": [
                {"snapshot_time": "2026-07-05T00:00:06+00:00", "index": "idx_a", "idx_tup_read": 160, "idx_scan": 20},
                {"snapshot_time": "2026-07-05T00:00:06+00:00", "index": "idx_b", "idx_tup_read": 150, "idx_scan": 20},
            ],
        },
        {
            "timestamp": "2026-07-05T00:00:20+00:00",
            "rows": [
                {"snapshot_time": "2026-07-05T00:00:11+00:00", "index": "idx_a", "idx_tup_read": 170, "idx_scan": 22},
                {"snapshot_time": "2026-07-05T00:00:11+00:00", "index": "idx_b", "idx_tup_read": 230, "idx_scan": 30},
            ],
        },
    ]

    result = build_chart_result(metric, samples, {})

    assert result["chart"]["kind"] == "stacked_column"
    assert result["chart"]["x_type"] == "datetime"
    assert result["series"] == [
        {
            "name": "idx_a",
            "unit": "ratio",
            "points": [{"t": "2026-07-05T00:00:06+00:00", "value": 6.0}],
        },
        {
            "name": "idx_b",
            "unit": "ratio",
            "points": [{"t": "2026-07-05T00:00:11+00:00", "value": 8.0}],
        },
    ]


def test_metric_item_inherits_sql_source_text_from_source_query() -> None:
    planned = PlannedItem(
        item_id="snapshot_charts_db.database_transaction_rate",
        section_id="snapshot_charts_db",
        item_key="database_transaction_rate",
        title="Database Transaction Rate",
        source_kind="metric",
        status="planned",
        source_id="database.transaction_rate",
        source_metadata={"metric_id": "database.transaction_rate"},
    )
    metric = {
        "title": "Database Transaction Rate",
        "source_query": "metrics.database_transaction_rate",
        "series": [{"name": "commits", "value_ref": "counters.xact_commit", "transform": "rate"}],
    }

    item = build_metric_item(
        planned,
        metric,
        db_snapshots=[],
        sampler_samples={},
        source_item_by_query={"metrics.database_transaction_rate": "__metric_sources.metrics_database_transaction_rate"},
        source_metadata_by_item={
            "__metric_sources.metrics_database_transaction_rate": {
                "source_text": "select xact_commit from pg_stat_database",
                "source_language": "sql",
                "semantic_columns": {"counters": {"xact_commit": "xact_commit"}},
            }
        },
    )

    assert item["source_metadata"]["source_language"] == "sql"
    assert "-- pg_diag metric: Database Transaction Rate" in item["source_metadata"]["source_text"]
    assert "-- source_query: metrics.database_transaction_rate" in item["source_metadata"]["source_text"]
    assert "select xact_commit from pg_stat_database" in item["source_metadata"]["source_text"]


def test_chart_can_preserve_configured_series_order() -> None:
    metric = {
        "chart": {"kind": "stacked_area", "unit": "bytes", "series_order": "configured"},
        "series": [
            {
                "name": "Application memory",
                "value_ref": "application_bytes",
                "transform": "gauge",
                "unit": "bytes",
                "color": "#00cc00",
            },
            {"name": "Free", "value_ref": "free_bytes", "transform": "gauge", "unit": "bytes"},
            {"name": "Buffers", "value_ref": "buffers_bytes", "transform": "gauge", "unit": "bytes"},
        ],
    }
    samples = [
        {
            "timestamp": "2026-07-05T00:00:00+00:00",
            "rows": [{"application_bytes": 300, "free_bytes": 100, "buffers_bytes": 50}],
        }
    ]

    result = build_chart_result(metric, samples, {})

    assert [series["name"] for series in result["series"]] == ["Application memory", "Free", "Buffers"]
    assert result["series"][0]["color"] == "#00cc00"


def test_cpu_utilization_stacked_chart_omits_total_series() -> None:
    metric = {
        "chart": {"kind": "stacked_area", "unit": "%", "series_order": "configured"},
        "series": [
            {"name": "user", "value_ref": "user_pct", "transform": "gauge", "unit": "%", "color": "#00cc00"},
            {"name": "system", "value_ref": "system_pct", "transform": "gauge", "unit": "%", "color": "#ff0000"},
            {"name": "iowait", "value_ref": "iowait_pct", "transform": "gauge", "unit": "%", "color": "#ffcc00"},
            {"name": "steal", "value_ref": "steal_pct", "transform": "gauge", "unit": "%", "color": "#ff6600"},
            {"name": "idle", "value_ref": "idle_pct", "transform": "gauge", "unit": "%", "color": "#9aa0a6"},
        ],
    }
    samples = [
        {
            "timestamp": "2026-07-05T00:00:00+00:00",
            "rows": [
                {
                    "user_pct": 10.0,
                    "system_pct": 3.0,
                    "iowait_pct": 1.0,
                    "steal_pct": 0.5,
                    "idle_pct": 85.5,
                    "util_pct": 13.5,
                }
            ],
        }
    ]

    result = build_chart_result(metric, samples, {})

    assert result["chart"]["kind"] == "stacked_area"
    assert [series["name"] for series in result["series"]] == ["user", "system", "iowait", "steal", "idle"]
    assert [series["color"] for series in result["series"]] == [
        "#00cc00",
        "#ff0000",
        "#ffcc00",
        "#ff6600",
        "#9aa0a6",
    ]


def test_sampler_metric_item_embeds_bash_source_text() -> None:
    planned = PlannedItem(
        item_id="snapshot_charts_os.os_cpu_utilization",
        section_id="snapshot_charts_os",
        item_key="os_cpu_utilization",
        title="CPU Utilization",
        source_kind="metric",
        status="planned",
        source_id="os.cpu_utilization",
        source_metadata={"metric_id": "os.cpu_utilization", "source_sampler": "os.cpu"},
    )
    metric = {
        "title": "CPU Utilization",
        "source_sampler": "os.cpu",
        "series": [{"name": "total", "value_ref": "util_pct", "transform": "gauge"}],
    }

    item = build_metric_item(
        planned,
        metric,
        db_snapshots=[],
        sampler_samples={"os.cpu": []},
        source_item_by_query={},
        source_metadata_by_item={},
        sampler_metadata={
            "source_language": "bash",
            "source_text": "#!/bin/sh\ncat /proc/stat\n",
        },
    )

    assert item["source_metadata"]["source_language"] == "bash"
    assert "# pg_diag metric: CPU Utilization" in item["source_metadata"]["source_text"]
    assert "# source_sampler: os.cpu" in item["source_metadata"]["source_text"]
    assert "cat /proc/stat" in item["source_metadata"]["source_text"]
