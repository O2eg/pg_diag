from __future__ import annotations

import re
from pathlib import Path

import pytest

from pg_diag.content_loader import ContentLoadError, iter_report_items, load_content, load_yaml_file
from pg_diag.planner import build_plan
from pg_diag.runtime_config import REMOTE_DB_ONLY_COLLECTION_MODE, SNAPSHOT_MODE, SNAPSHOTS_MODE
from pg_diag.validator import ALLOWED_ITEM_TAGS, has_errors, validate_content
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
        if "python" in item:
            assert item["python"] in content.pythons


def test_report_items_have_exactly_one_source(content_path: Path) -> None:
    content = load_content(content_path)
    for _section_id, _item_key, _item_id, item in iter_report_items(content):
        assert len({"query", "script", "metric", "python"}.intersection(item)) == 1


def test_report_items_have_allowed_tags(content_path: Path) -> None:
    content = load_content(content_path)
    for _section_id, _item_key, item_id, item in iter_report_items(content):
        tags = item.get("tags") or []
        assert tags, item_id
        assert len(tags) == len(set(tags)), item_id
        assert set(tags).issubset(ALLOWED_ITEM_TAGS), item_id


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


def test_overview_instructions_have_interpretation_sections(content_path: Path) -> None:
    content = load_content(content_path)
    overview_item_ids = [
        item_id
        for section_id, _item_key, item_id, _item in iter_report_items(content)
        if section_id == "overview"
    ]
    assert len(overview_item_ids) == 11
    for item_id in overview_item_ids:
        text = content.instructions[item_id]["text"]
        assert "## What to watch" in text, item_id
        assert "## Common fault causes" in text, item_id


def test_os_instructions_define_complete_interpretation_contract(content_path: Path) -> None:
    content = load_content(content_path)
    os_item_ids = [
        item_id
        for section_id, _item_key, item_id, _item in iter_report_items(content)
        if section_id == "os"
    ]
    assert len(os_item_ids) == 47
    for item_id in os_item_ids:
        text = content.instructions[item_id]["text"]
        assert "This instruction belongs to" in text, item_id
        assert "## What to watch" in text, item_id
        assert "## Automatic evaluation" in text, item_id
        assert "## Common fault causes" in text, item_id


def test_activity_lock_instructions_define_complete_interpretation_contract(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    item_ids = [
        item_id
        for section_id, _item_key, item_id, _item in iter_report_items(content)
        if section_id == "activity_locks"
    ]
    assert len(item_ids) == 10
    for item_id in item_ids:
        text = content.instructions[item_id]["text"]
        assert "This instruction belongs to" in text, item_id
        assert "## What to watch" in text, item_id
        assert "## Automatic evaluation" in text, item_id
        assert "## Common fault causes" in text, item_id


def test_activity_lock_sql_uses_supported_bounded_semantics(content_path: Path) -> None:
    content = load_content(content_path)
    query_root = content.path / "queries"

    connection_sql = (query_root / "activity/connection_pressure.sql").read_text(
        encoding="utf-8"
    ).lower()
    assert "backend_type = 'client backend'" in connection_sql
    assert "current_setting('reserved_connections', true)" in connection_sql
    assert "'cluster'::text as scope" in connection_sql

    lock_waits_sql = (query_root / "locks/lock_waits.sql").read_text(encoding="utf-8").lower()
    assert "pg_blocking_pids(activity.pid)" in lock_waits_sql
    assert "waitstart" in lock_waits_sql
    assert "limit 10000" in lock_waits_sql
    assert "blocked.relation = blocker.relation" not in lock_waits_sql

    wait_sql = (query_root / "activity/wait_events.sql").read_text(encoding="utf-8").lower()
    sampled_wait_sql = (query_root / "metrics/activity_wait_sample_profile.sql").read_text(
        encoding="utf-8"
    ).lower()
    for sql in (wait_sql, sampled_wait_sql):
        assert "pid <> pg_backend_pid()" in sql
        assert "active without wait event" in sql
        assert "'cpu'" not in sql
        assert "limit 100" in sql


def test_sql_workload_instructions_define_complete_interpretation_contract(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    item_ids = [
        item_id
        for section_id, _item_key, item_id, _item in iter_report_items(content)
        if section_id == "sql_workload"
    ]
    assert len(item_ids) == 7
    for item_id in item_ids:
        text = content.instructions[item_id]["text"]
        assert "This instruction belongs to" in text, item_id
        assert "## What to watch" in text, item_id
        assert "## Automatic evaluation" in text, item_id
        assert "## Common fault causes" in text, item_id


def test_sql_workload_queries_use_complete_bounded_statement_identity(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    top_query_ids = {
        "statements.top_by_total_time",
        "statements.top_by_mean_time",
        "statements.top_by_calls",
        "statements.top_by_io",
        "statements.top_by_temp_io",
        "statements.top_by_wal",
    }

    for query_id in top_query_ids:
        query = content.queries[query_id]
        assert query["optional"] is True
        assert query["collection"] == {"default": "once", "supports": ["once"]}
        for variant in query["variants"]:
            sql = (content.path / "queries" / variant["sql_file"]).read_text(
                encoding="utf-8"
            ).lower()
            assert "s.dbid" in sql, query_id
            assert "s.userid" in sql, query_id
            assert "s.queryid" in sql, query_id
            assert "s.toplevel" in sql, query_id
            assert "limit 50" in sql, query_id
            assert "pg_diag_internal_severity" in sql, query_id


def test_sql_workload_version_specific_columns(content_path: Path) -> None:
    content = load_content(content_path)

    pg16 = select_query_variant(
        "statements.top_by_total_time",
        content.queries["statements.top_by_total_time"],
        160000,
    )
    pg17 = select_query_variant(
        "statements.top_by_total_time",
        content.queries["statements.top_by_total_time"],
        170000,
    )
    pg18 = select_query_variant(
        "statements.top_by_total_time",
        content.queries["statements.top_by_total_time"],
        180000,
    )
    pg16_sql = (content.path / "queries" / pg16.variant["sql_file"]).read_text(encoding="utf-8")
    pg17_sql = (content.path / "queries" / pg17.variant["sql_file"]).read_text(encoding="utf-8")
    pg18_sql = (content.path / "queries" / pg18.variant["sql_file"]).read_text(encoding="utf-8")

    assert "stats_since" not in pg16_sql
    assert "shared_blk_read_time" in pg17_sql
    assert "stats_since" in pg17_sql
    assert "parallel_workers_to_launch" not in pg17_sql
    assert "parallel_workers_to_launch" in pg18_sql
    assert "parallel_workers_launched" in pg18_sql


def test_statement_delta_sources_do_not_collapse_hidden_query_ids(content_path: Path) -> None:
    content = load_content(content_path)
    expected_keys = [
        "dimensions.database_id",
        "dimensions.user_id",
        "dimensions.query_id",
        "dimensions.toplevel",
    ]
    metric_ids = {
        "statements.total_time_delta",
        "statements.io_delta",
        "statements.wal_delta",
    }
    for metric_id in metric_ids:
        metric = content.metrics[metric_id]
        assert metric["table"]["key_refs"] == expected_keys
        source = content.queries[metric["source_query"]]
        assert source["optional"] is True
        for variant in source["variants"]:
            sql = (content.path / "queries" / variant["sql_file"]).read_text(
                encoding="utf-8"
            ).lower()
            assert "s.queryid is not null" in sql, metric_id
            assert "s.toplevel" in sql, metric_id
            assert "''::text as query" in sql, metric_id


def test_snapshot_delta_workload_defines_complete_interval_contract(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    item_ids = [
        item_id
        for section_id, _item_key, item_id, _item in iter_report_items(content)
        if section_id == "snapshot_delta_workload"
    ]

    assert len(item_ids) == 9
    for item_id in item_ids:
        text = content.instructions[item_id]["text"]
        assert "This instruction belongs to" in text, item_id
        assert "## What to watch" in text, item_id
        assert "## Automatic evaluation" in text, item_id
        assert "## Interval coverage" in text, item_id
        assert "## Common fault causes" in text, item_id

        metric_ref = next(
            item["metric"]
            for section_id, _item_key, report_item_id, item in iter_report_items(content)
            if section_id == "snapshot_delta_workload" and report_item_id == item_id
        )
        assert metric_ref in content.metrics
        assert content.metrics[metric_ref]["requires_collection"] == "window_endpoints"


def test_snapshot_delta_sources_keep_bounded_oid_identity_and_reset_epochs(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    expected = {
        "database.workload_delta": (["dimensions.database_id"], None),
        "statements.total_time_delta": (
            [
                "dimensions.database_id",
                "dimensions.user_id",
                "dimensions.query_id",
                "dimensions.toplevel",
            ],
            50,
        ),
        "statements.io_delta": (
            [
                "dimensions.database_id",
                "dimensions.user_id",
                "dimensions.query_id",
                "dimensions.toplevel",
            ],
            50,
        ),
        "statements.wal_delta": (
            [
                "dimensions.database_id",
                "dimensions.user_id",
                "dimensions.query_id",
                "dimensions.toplevel",
            ],
            50,
        ),
        "objects.table_dml_delta": (
            ["dimensions.database_id", "dimensions.relation_id"],
            200,
        ),
        "objects.table_scan_delta": (
            ["dimensions.database_id", "dimensions.relation_id"],
            200,
        ),
        "objects.table_io_delta": (
            ["dimensions.database_id", "dimensions.relation_id"],
            200,
        ),
        "objects.index_usage_delta": (
            ["dimensions.database_id", "dimensions.index_id"],
            200,
        ),
        "objects.function_time_delta": (
            ["dimensions.database_id", "dimensions.function_id"],
            100,
        ),
    }

    for metric_id, (key_refs, source_limit) in expected.items():
        metric = content.metrics[metric_id]
        assert metric["table"]["key_refs"] == key_refs
        assert metric["table"]["epoch_refs"], metric_id
        source = content.queries[metric["source_query"]]
        assert source["collection"] == {
            "default": "window_endpoints",
            "supports": ["once", "window_endpoints"],
        }
        for variant in source["variants"]:
            sql = (content.path / "queries" / variant["sql_file"]).read_text(
                encoding="utf-8"
            ).lower()
            assert "order by" not in sql if source_limit is None else "order by" in sql
            assert "limit" not in sql if source_limit is None else f"limit {source_limit}" in sql
            assert not re.search(r"\bpg_stat(?:ements)?_reset\w*\s*\(", sql), metric_id


def test_snapshot_delta_version_epochs_and_database_output_are_complete(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    database_sql = (
        content.path / "queries/metrics/database_workload_delta.sql"
    ).read_text(encoding="utf-8").lower()
    for column in (
        "stats_reset",
        "blks_read",
        "blks_hit",
        "tup_returned",
        "tup_fetched",
        "tup_inserted",
        "tup_updated",
        "tup_deleted",
        "blk_read_time",
        "blk_write_time",
    ):
        assert column in database_sql

    for metric_id in (
        "statements.total_time_delta",
        "statements.io_delta",
        "statements.wal_delta",
    ):
        source = content.queries[content.metrics[metric_id]["source_query"]]
        pg16 = select_query_variant(source["title"], source, 160000)
        pg17 = select_query_variant(source["title"], source, 170000)
        pg16_sql = (content.path / "queries" / pg16.variant["sql_file"]).read_text(
            encoding="utf-8"
        ).lower()
        pg17_sql = (content.path / "queries" / pg17.variant["sql_file"]).read_text(
            encoding="utf-8"
        ).lower()
        assert "pg_stat_statements_info" in pg16_sql
        assert "stats_since" not in pg16_sql
        assert "pg_stat_statements_info" in pg17_sql
        assert "stats_since" in pg17_sql

    database_metric = content.metrics["database.workload_delta"]
    database_columns = {
        column["name"]: column for column in database_metric["table"]["columns"]
    }
    assert database_columns["commit_delta_raw"]["transform"] == "delta"
    assert database_columns["commit_delta"]["transform"] == "delta_minus_context"
    assert database_columns["commits_per_sec"]["transform"] == "rate_minus_context"
    assert database_metric["evaluation"]["rules"][0]["severity"] == "medium"
    assert content.metrics["objects.table_scan_delta"]["evaluation"]["rules"][0][
        "severity"
    ] == "medium"


def test_pg_stat_statements_capability_preserves_hidden_setting_state(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    variant = content.queries["statements.pg_stat_statements_capabilities"]["variants"][0]
    sql = (content.path / "queries" / variant["sql_file"]).read_text(encoding="utf-8")

    assert "pg_read_all_stats" in sql
    assert "pg_read_all_settings" in sql
    assert "'<hidden>'" in sql
    assert "required_view_columns" in sql
    assert "parallel_workers_to_launch" in sql
    assert "track_functions" not in sql
    assert "track_wal_io_timing" not in sql


def test_os_shell_scripts_do_not_require_fixed_sbin_paths(content_path: Path) -> None:
    content = load_content(content_path)
    for script_id, manifest in content.scripts.items():
        if not script_id.startswith("os."):
            continue
        script = (content.path / "scripts" / manifest["script_file"]).read_text(encoding="utf-8")
        assert "/sbin/sysctl" not in script, script_id


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


def test_high_cardinality_metric_sources_keep_order_and_limit(content_path: Path) -> None:
    content = load_content(content_path)
    bounded_metrics = {
        metric_id: metric
        for metric_id, metric in content.metrics.items()
        if metric.get("source_query")
        and metric_id != "activity.wait_sample_profile"
        and (metric.get("top_n") or (metric.get("table") and metric_id != "database.workload_delta"))
    }
    assert len(bounded_metrics) == 24

    for metric_id, metric in bounded_metrics.items():
        query = content.queries[metric["source_query"]]
        for variant in query.get("variants") or []:
            sql = (content.path / "queries" / variant["sql_file"]).read_text(encoding="utf-8")
            assert re.search(r"\border\s+by\b", sql, re.IGNORECASE), metric_id
            assert re.search(r"\blimit\s+\d+\b", sql, re.IGNORECASE), metric_id


def test_overview_automatic_checks_expose_severity_evidence(content_path: Path) -> None:
    content = load_content(content_path)
    evaluated_query_ids = {
        "cluster.settings",
        "database.database_stats",
        "security.security_logging_settings",
        "security.password_encryption",
        "security.password_complexity",
        "security.auth_timeout_delay",
        "security.listen_addresses_exposure",
        "security.tls_server_configuration",
        "security.weak_tls_ciphers",
    }
    for query_id in evaluated_query_ids:
        for variant in content.queries[query_id].get("variants") or []:
            sql = (content.path / "queries" / variant["sql_file"]).read_text(encoding="utf-8")
            assert re.search(
                r"\b(risk_level|pg_diag_internal_severity)\b",
                sql,
                re.IGNORECASE,
            ), query_id


def test_pg18_database_stats_exposes_parallel_worker_counters(content_path: Path) -> None:
    content = load_content(content_path)
    selection = select_query_variant(
        "database.database_stats",
        content.queries["database.database_stats"],
        180000,
    )
    sql = (content.path / "queries" / selection.variant["sql_file"]).read_text(encoding="utf-8")

    assert "parallel_workers_to_launch" in sql
    assert "parallel_workers_launched" in sql


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
        == "database_stats_pg15_pg17"
    )
    assert (
        select_query_variant("database.database_stats", query, 180000).variant["id"]
        == "database_stats_pg18_plus"
    )
    assert (
        select_query_variant("database.database_stats", query, 170000).variant["id"]
        == "database_stats_pg15_pg17"
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
    assert by_id["os.kernel_version"].reason == "no data because remote call"
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
    assert by_id["overview.pg_settings"].source_metadata["evaluation"] == {
        "summary_title": "PostgreSQL settings require review",
        "recommendation": (
            "Review pending-restart settings and validate work_mem against concurrency "
            "and query spill evidence before changing it globally."
        ),
    }
    assert by_id["storage_vacuum.autovacuum_queue"].source_metadata["display"]["default_sort"] == {
        "column": "autovacuum_overdue_factor",
        "direction": "desc",
    }
    assert by_id["overview.server_version"].source_metadata["instructions"]["format"] == "markdown"
    assert by_id["overview.server_version"].source_metadata["tags"] == ["Configuration"]
    assert by_id["activity_locks.lock_waits"].source_metadata["tags"] == ["Locks", "Waits", "Sessions"]
    assert by_id["activity_locks.lock_waits"].source_metadata["render"]["empty_message"] == "No lock waits detected."
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
    assert by_source["database.database_stats"].collection_scope == "once"
    assert by_source["io.pg_stat_io"].collection_scope == "once"
    assert by_source["metrics.database_transaction_rate"].collection_scope == "every_snapshot"
    assert by_source["metrics.wal_growth_rate"].collection_scope == "every_snapshot"
    assert by_source["metrics.io_read_write_rate"].collection_scope == "every_snapshot"
    assert by_source["metrics.database_workload_delta"].collection_scope == "window_endpoints"
    assert by_source["metrics.statements_total_time_delta"].collection_scope == "window_endpoints"
    assert by_source["objects.table_workload"].collection_scope == "once"
    assert by_source["objects.table_io"].collection_scope == "once"
    assert by_source["objects.index_workload"].collection_scope == "once"
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
    assert by_source["statements.top_by_total_time"].collection_scope == "once"
    assert by_source["objects.table_workload"].collection_scope == "once"
    assert by_source["backend.activity"].collection_scope == "once"
    assert by_id["activity_locks.wait_event_sample_profile"].source_kind == "metric"
    assert by_id["activity_locks.pg_wait_sampling_capabilities"].source_kind == "query"
    assert by_id["backend_os.postgres_process_tree"].source_kind == "script"
    assert by_id["backend_os.postgres_process_tree"].script_file == "os/postgres_process_tree.sh"
    assert by_id["snapshot_delta_workload.sql_time_delta"].source_metadata["display"]["default_sort"] == {
        "column": "exec_time_ms_per_sec",
        "direction": "desc",
    }
    assert by_id["backend_os.backend_proc_cpu"].source_metadata["source_sampler"] == "os.backend_proc"


def test_snapshots_repeat_only_chart_query_sources(content_path: Path) -> None:
    content = load_content(content_path)
    plan = build_plan(content, 180000, mode=SNAPSHOTS_MODE)
    metrics_by_source = {
        metric.get("source_query"): metric
        for metric in content.metrics.values()
        if metric.get("source_query")
    }

    visible_queries = [
        item
        for item in plan.items
        if item.source_kind == "query" and not item.source_metadata.get("internal")
    ]
    assert visible_queries
    assert {item.collection_scope for item in visible_queries} == {"once"}

    repeated_queries = [
        item
        for item in plan.items
        if item.source_kind == "query" and item.collection_scope == "every_snapshot"
    ]
    assert repeated_queries
    for item in repeated_queries:
        metric = metrics_by_source[item.source_id]
        assert metric.get("result") != "table"
        assert not metric.get("table")

    endpoint_queries = [
        item
        for item in plan.items
        if item.source_kind == "query" and item.collection_scope == "window_endpoints"
    ]
    assert endpoint_queries
    for item in endpoint_queries:
        metric = metrics_by_source[item.source_id]
        assert metric.get("result") == "table" or metric.get("table")

    sampler_table_metrics = [
        metric
        for metric in content.metrics.values()
        if metric.get("source_sampler")
        and (metric.get("result") == "table" or metric.get("table"))
    ]
    assert sampler_table_metrics
    for metric in sampler_table_metrics:
        assert metric.get("requires_collection") == "window_endpoints"


def test_metric_semantic_refs_are_resolvable(content_path: Path) -> None:
    content = load_content(content_path)
    issues = validate_content(content)
    assert not has_errors([issue for issue in issues if issue.code == "metric_ref"])


def test_validator_rejects_repeated_sampler_table(content_path: Path) -> None:
    content = load_content(content_path)
    content.metrics["backend.proc_cpu_top"]["requires_collection"] = "every_snapshot"

    issues = validate_content(content)

    assert any(
        issue.code == "metric_collection"
        and issue.location == "metric:backend.proc_cpu_top"
        for issue in issues
    )


def test_validator_rejects_unknown_query_evaluation_keys(content_path: Path) -> None:
    content = load_content(content_path)
    content.queries["cluster.settings"]["evaluation"]["threshold_magic"] = 1

    issues = validate_content(content)

    assert any(
        issue.code == "evaluation"
        and issue.location == "query:cluster.settings"
        and "threshold_magic" in issue.message
        for issue in issues
    )
