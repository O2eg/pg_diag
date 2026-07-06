from __future__ import annotations

import re
from pathlib import Path

import pytest

from pg_diag.content_loader import ContentLoadError, iter_report_items, load_content, load_yaml_file
from pg_diag.planner import build_plan
from pg_diag.runtime_config import REMOTE_DB_ONLY_COLLECTION_MODE, SNAPSHOT_MODE, SNAPSHOTS_MODE
from pg_diag.validator import has_errors, validate_content
from pg_diag.versioning import select_query_variant


def test_content_manifests_are_valid(content_path: Path) -> None:
    content = load_content(content_path)
    issues = validate_content(content)
    assert not issues


def test_report_references_exist(content_path: Path) -> None:
    content = load_content(content_path)
    for _section_id, _item_key, _item_id, item in iter_report_items(content):
        if "query" in item:
            assert item["query"] in content.queries
        if "script" in item:
            assert item["script"] in content.scripts
        if "metric" in item:
            assert item["metric"] in content.metrics


def test_report_items_have_exactly_one_source(content_path: Path) -> None:
    content = load_content(content_path)
    for _section_id, _item_key, _item_id, item in iter_report_items(content):
        assert len({"query", "script", "metric"}.intersection(item)) == 1


def test_report_items_have_markdown_instructions(content_path: Path) -> None:
    content = load_content(content_path)
    item_ids = []
    for _section_id, _item_key, item_id, _item in iter_report_items(content):
        item_ids.append(item_id)
        instruction = content.instructions.get(item_id)
        assert instruction, item_id
        assert instruction["format"] == "markdown"
        assert instruction["path"].endswith(".md")
        assert "## What this item shows" in instruction["text"]
        assert "## Checklist" in instruction["text"]
    assert set(content.instructions) == set(item_ids)


def test_query_manifests_define_default_sort(content_path: Path) -> None:
    content = load_content(content_path)
    for query_id, manifest in content.queries.items():
        default_sort = (manifest.get("display") or {}).get("default_sort") or {}
        assert default_sort.get("column"), query_id
        assert default_sort.get("direction") in {"asc", "desc"}, query_id


def test_sql_metric_sources_expose_snapshot_time(content_path: Path) -> None:
    content = load_content(content_path)
    query_ids = {
        metric["source_query"]
        for metric in content.metrics.values()
        if metric.get("source_query")
    }
    for query_id in sorted(query_ids):
        query = content.queries[query_id]
        for variant in query.get("variants") or []:
            sql_file = variant["sql_file"]
            sql = (content.path / "queries" / sql_file).read_text(encoding="utf-8")
            assert "snapshot_time" in sql.lower(), f"{query_id} variant {variant['id']} lacks snapshot_time"


def test_sql_query_id_columns_expose_query_text(content_path: Path) -> None:
    content = load_content(content_path)
    query_id_column_re = re.compile(r"\bas\s+([a-z_]*query_id)\b", re.IGNORECASE)

    for query_id, query in content.queries.items():
        for variant in query.get("variants") or []:
            sql_file = variant["sql_file"]
            sql = (content.path / "queries" / sql_file).read_text(encoding="utf-8")
            for match in query_id_column_re.finditer(sql):
                query_id_column = match.group(1).lower()
                query_column = query_id_column.removesuffix("_id")
                query_column_re = re.compile(rf"\bas\s+{re.escape(query_column)}\b", re.IGNORECASE)
                assert query_column_re.search(sql), (
                    f"{query_id} variant {variant['id']} exposes {query_id_column} "
                    f"without {query_column}"
                )


def test_no_table_columns_in_report_layout(content_path: Path) -> None:
    content = load_content(content_path)
    forbidden = {"columns", "theader", "fields"}
    for _section_id, _item_key, _item_id, item in iter_report_items(content):
        assert not forbidden.intersection(item)


def test_yaml_duplicate_keys_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("root:\n  item: 1\n  item: 2\n", encoding="utf-8")
    with pytest.raises(ContentLoadError, match="Duplicate YAML key"):
        load_yaml_file(path)


def test_variant_selection_by_supported_pg_version(content_path: Path) -> None:
    content = load_content(content_path)
    query = content.queries["database.database_stats"]

    assert select_query_variant("database.database_stats", query, 140000).variant["id"] == "database_stats_pg14"
    assert (
        select_query_variant("database.database_stats", query, 150000).variant["id"]
        == "database_stats_pg15_plus"
    )
    assert (
        select_query_variant("database.database_stats", query, 180000).variant["id"]
        == "database_stats_pg15_plus"
    )


def test_unsupported_pg_version_boundaries(content_path: Path) -> None:
    content = load_content(content_path)
    plan_low = build_plan(content, 130000)
    plan_high = build_plan(content, 190000)

    assert not plan_low.supported_server_version
    assert not plan_high.supported_server_version
    assert all(item.status == "unsupported" for item in plan_low.items)
    assert all(item.status == "unsupported" for item in plan_high.items)


def test_snapshot_collection_policy(content_path: Path) -> None:
    content = load_content(content_path)
    plan = build_plan(
        content,
        180000,
        mode=SNAPSHOT_MODE,
        collection_mode=REMOTE_DB_ONLY_COLLECTION_MODE,
    )

    by_id = {item.item_id: item for item in plan.items}
    assert by_id["os.kernel_version"].status == "skipped"
    assert by_id["os.kernel_version"].reason == "no data bacause remote call"
    assert by_id["snapshot_charts_db.database_transaction_rate"].status == "skipped"
    assert by_id["snapshot_charts_db.database_transaction_rate"].reason == "requires snapshots mode"


def test_plan_exposes_query_default_sort(content_path: Path) -> None:
    content = load_content(content_path)
    plan = build_plan(content, 180000)
    by_id = {item.item_id: item for item in plan.items}

    assert by_id["overview.pg_settings"].source_metadata["display"]["default_sort"] == {
        "column": "setting_name",
        "direction": "asc",
    }
    assert by_id["storage_vacuum.autovacuum_queue"].source_metadata["display"]["default_sort"] == {
        "column": "autovacuum_overdue_factor",
        "direction": "desc",
    }
    assert by_id["overview.server_version"].source_metadata["instructions"]["format"] == "markdown"
    assert "## Checklist" in by_id["overview.server_version"].source_metadata["instructions"]["text"]
    assert by_id["overview.server_version"].source_metadata["query_usage"] == {
        "query_id": "cluster.server_version",
        "isolation": "isolated",
        "item_count": 1,
        "item_ids": ["overview.server_version"],
        "other_item_ids": [],
    }


def test_snapshots_promotes_metric_sources(content_path: Path) -> None:
    content = load_content(content_path)
    plan = build_plan(content, 180000, mode=SNAPSHOTS_MODE)
    by_source = {item.source_id: item for item in plan.items if item.source_kind == "query"}
    by_id = {item.item_id: item for item in plan.items}
    assert by_source["database.database_stats"].collection_scope == "every_snapshot"
    assert by_source["io.pg_stat_io"].collection_scope == "once:latest"
    assert by_source["metrics.database_transaction_rate"].collection_scope == "every_snapshot"
    assert by_source["metrics.wal_growth_rate"].collection_scope == "every_snapshot"
    assert by_source["metrics.io_read_write_rate"].collection_scope == "every_snapshot"
    assert by_source["objects.table_workload"].collection_scope == "every_snapshot"
    assert by_source["objects.table_io"].collection_scope == "every_snapshot"
    assert by_source["objects.index_workload"].collection_scope == "every_snapshot"
    assert by_source["metrics.database_transaction_rate"].source_metadata["internal"] is True
    database_usage = by_id["overview.database_stats"].source_metadata["query_usage"]
    assert database_usage["query_id"] == "database.database_stats"
    assert database_usage["isolation"] == "isolated"
    assert database_usage["item_count"] == 1
    assert database_usage["item_ids"] == ["overview.database_stats"]
    assert database_usage["other_item_ids"] == []
    assert by_id["snapshot_charts_db.database_transaction_rate"].source_metadata["source_query"] == (
        "metrics.database_transaction_rate"
    )
    metric_usage = by_id["snapshot_charts_db.database_tuple_dml_rate"].source_metadata["query_usage"]
    assert metric_usage["query_id"] == "metrics.database_tuple_dml_rate"
    assert metric_usage["isolation"] == "isolated"
    assert metric_usage["item_ids"] == ["snapshot_charts_db.database_tuple_dml_rate"]
    assert metric_usage["other_item_ids"] == []
    assert "query_usage" not in by_id["snapshot_charts_os.os_cpu_utilization"].source_metadata
    assert by_id["snapshot_charts_db.tables_top_dml_rate"].source_metadata["chart"]["kind"] == "stacked_column"
    for item_id in (
        "snapshot_charts_db.indexes_top_reads_per_scan",
        "snapshot_charts_db.indexes_top_fetches_per_scan",
        "snapshot_charts_db.indexes_top_reads_per_fetch",
    ):
        assert by_id[item_id].source_metadata["chart"]["kind"] == "stacked_column"
        assert content.metrics[by_id[item_id].source_id]["top_n"]["mode"] == "interval"


def test_sql_backed_report_items_have_isolated_query_usage(content_path: Path) -> None:
    content = load_content(content_path)
    plan = build_plan(content, 180000, mode=SNAPSHOTS_MODE)

    source_queries = [
        metric["source_query"]
        for metric in content.metrics.values()
        if metric.get("source_query")
    ]
    assert len(source_queries) == len(set(source_queries))

    for item in plan.items:
        if item.source_metadata.get("internal"):
            continue
        usage = item.source_metadata.get("query_usage")
        if not usage:
            continue
        assert usage["isolation"] == "isolated", item.item_id
        assert usage["item_count"] == 1, item.item_id
        assert usage["item_ids"] == [item.item_id], item.item_id
        assert usage["other_item_ids"] == [], item.item_id


def test_snapshot_chart_sections_are_split(content_path: Path) -> None:
    content = load_content(content_path)
    plan = build_plan(content, 180000, mode=SNAPSHOTS_MODE)
    by_id = {item.item_id: item for item in plan.items}

    assert "snapshot_charts_os.os_cpu_utilization" in by_id
    assert "snapshot_charts_db.database_transaction_rate" in by_id
    assert "snapshot_charts_db.database_tuple_dml_rate" in by_id
    assert "snapshot_charts_db.tables_top_tuple_access_rate" in by_id
    assert "snapshot_charts_db.indexes_top_scan_rate" in by_id
    assert by_id["snapshot_charts_os.os_cpu_utilization"].source_metadata["source_sampler"] == "os.cpu"


def test_workload_sections_and_delta_dependencies_are_planned(content_path: Path) -> None:
    content = load_content(content_path)
    plan = build_plan(content, 180000, mode=SNAPSHOTS_MODE)
    section_ids = {section["section_id"] for section in plan.sections}
    by_source = {item.source_id: item for item in plan.items if item.source_kind == "query"}
    by_id = {item.item_id: item for item in plan.items}

    assert {"sql_workload", "snapshot_delta_workload", "object_workload", "backend_os"}.issubset(section_ids)
    assert "wait_profile" not in section_ids
    assert by_source["statements.top_by_total_time"].collection_scope == "every_snapshot"
    assert by_source["objects.table_workload"].collection_scope == "every_snapshot"
    assert by_source["backend.activity"].collection_scope == "every_snapshot"
    assert by_id["activity_locks.wait_event_sample_profile"].source_kind == "metric"
    assert by_id["activity_locks.pg_wait_sampling_capabilities"].source_kind == "query"
    assert by_id["backend_os.postgres_process_tree"].source_kind == "script"
    assert by_id["backend_os.postgres_process_tree"].script_file == "os/postgres_process_tree.sh"
    assert by_id["snapshot_delta_workload.sql_time_delta"].source_metadata["display"]["default_sort"] == {
        "column": "exec_time_ms_per_sec",
        "direction": "desc",
    }
    assert by_id["backend_os.backend_proc_cpu"].source_metadata["source_sampler"] == "os.backend_proc"


def test_metric_semantic_refs_are_resolvable(content_path: Path) -> None:
    content = load_content(content_path)
    issues = validate_content(content)
    assert not has_errors([issue for issue in issues if issue.code == "metric_ref"])
