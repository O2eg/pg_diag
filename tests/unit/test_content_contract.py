from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import re
import subprocess

import pytest

from pg_diag.artifact import create_artifact
from pg_diag.content_loader import ContentLoadError, iter_report_items, load_content, load_yaml_file
from pg_diag.planner import build_plan
from pg_diag.presentation import apply_presentation_contract, resolve_column_descriptor
from pg_diag.runtime_config import (
    HOST_COMMAND_TIMEOUT_SECONDS,
    REMOTE_DB_ONLY_COLLECTION_MODE,
    ONE_SHOT_MODE,
    SNAPSHOTS_MODE,
)
from pg_diag.validator import has_errors, validate_content
from pg_diag.versioning import select_query_variant


def test_content_manifests_are_valid(content_path: Path) -> None:
    content = load_content(content_path)
    issues = validate_content(content)
    assert not issues


def test_buffer_cache_section_has_ten_independent_chart_sources(content_path: Path) -> None:
    content = load_content(content_path)
    section = content.report["sections"]["buffer_cache"]

    assert len(section["items"]) == 10
    metric_ids = [item["metric"] for item in section["items"].values()]
    source_ids = [content.metrics[metric_id]["source_query"] for metric_id in metric_ids]
    assert len(source_ids) == len(set(source_ids)) == 10
    assert all(content.queries[source_id].get("optional") is not True for source_id in source_ids)


def test_relation_coverage_excludes_system_schemas(content_path: Path) -> None:
    sql = (content_path / "queries/buffer_cache/relation_coverage.sql").read_text(
        encoding="utf-8"
    )

    assert "join pg_catalog.pg_namespace n" in sql
    assert "n.nspname !~ '^pg_'" in sql
    assert "n.nspname <> 'information_schema'" in sql


def test_zero_disk_reads_have_an_explicit_empty_message(content_path: Path) -> None:
    content = load_content(content_path)
    item = content.report["sections"]["snapshot_charts_os"]["items"]["os_disk_read_throughput"]

    assert item["render"]["empty_message"] == (
        "No non-zero physical disk read throughput was observed during the snapshot window."
    )


def test_metric_table_columns_declare_output_types(content_path: Path) -> None:
    content = load_content(content_path)
    for metric_id, metric in content.metrics.items():
        for column in (metric.get("table") or {}).get("columns") or []:
            assert column.get("pg_type"), f"{metric_id}.{column.get('name')}"

    metrics = deepcopy(content.metrics)
    metrics["database.workload_delta"]["table"]["columns"][0].pop("pg_type")
    invalid = replace(content, metrics=metrics)

    issues = validate_content(invalid)

    assert any(
        issue.code == "metric_result"
        and "must define its output pg_type" in issue.message
        for issue in issues
    )

    metrics = deepcopy(content.metrics)
    metrics["io.activity_delta"]["table"]["columns"][3]["optional"] = "yes"
    invalid = replace(content, metrics=metrics)

    issues = validate_content(invalid)

    assert any(
        issue.code == "metric_result"
        and "optional must be boolean" in issue.message
        for issue in issues
    )


@pytest.mark.parametrize(
    ("name", "pg_type", "expected"),
    [
        ("blks_read_bytes_delta", "float8", ("integer", "counter_delta", "bytes")),
        ("total_blks_read_per_sec", "float8", ("decimal", "rate", "blocks/s")),
        ("plan_time_ms_per_sec", "float8", ("decimal", "rate", "milliseconds/s")),
        ("postmaster_uptime_s", "int8", ("decimal", "duration", "seconds")),
        ("clock", "int8", ("integer", "gauge", "hertz")),
        ("xact_start", "timestamptz", ("timestamp", "state", "none")),
        ("blocks_done_pct", "numeric", ("decimal", "gauge", "percent")),
        ("bytes_total", "int8", ("integer", "gauge", "bytes")),
        ("buffers_written_delta", "float8", ("integer", "counter_delta", "blocks")),
        ("buffers_backend_fsync_delta", "float8", ("integer", "counter_delta", "count")),
    ],
)
def test_presentation_rules_resolve_canonical_dimensions_without_rows(
    content_path: Path,
    name: str,
    pg_type: str,
    expected: tuple[str, str, str],
) -> None:
    content = load_content(content_path)

    descriptor = resolve_column_descriptor(
        content,
        {"name": name, "pg_type": pg_type},
        [],
        source_kind="query",
        source_id="test.synthetic",
        item_id="test.synthetic",
    )

    assert (
        descriptor["value_kind"],
        descriptor["semantic_role"],
        descriptor["unit"],
    ) == expected


def test_millisecond_duration_label_does_not_promise_a_fixed_display_scale(
    content_path: Path,
) -> None:
    content = load_content(content_path)

    descriptor = resolve_column_descriptor(
        content,
        {"name": "total_exec_time_ms", "pg_type": "float8"},
        [],
        source_kind="query",
        source_id="test.synthetic",
        item_id="test.synthetic",
    )

    assert descriptor["unit"] == "milliseconds"
    assert descriptor["label"] == "Total exec time"


def test_pg_settings_keeps_source_unit_separate_from_canonical_unit(content_path: Path) -> None:
    content = load_content(content_path)

    source_unit = resolve_column_descriptor(
        content,
        {"name": "source_unit", "pg_type": "text"},
        [],
        source_kind="query",
        source_id="cluster.settings",
        item_id="overview.pg_settings",
    )
    normalized_unit = resolve_column_descriptor(
        content,
        {"name": "unit_normalized", "pg_type": "text"},
        [],
        source_kind="query",
        source_id="cluster.settings",
        item_id="overview.pg_settings",
    )

    assert source_unit["quantity"] == "text"
    assert normalized_unit["quantity"] == "unit_code"


def test_chart_delta_uses_exact_counter_delta_descriptor(content_path: Path) -> None:
    content = load_content(content_path)
    artifact = {
        "items": {
            "snapshot_charts_db.database_temp_files_delta": {
                "source_kind": "metric",
                "source_metadata": {"metric_id": "database.temp_files_delta"},
                "result": {
                    "kind": "chart",
                    "chart": {"kind": "column", "unit": "files"},
                    "series": [
                        {
                            "name": "temp files (db)",
                            "unit": "files",
                            "points": [
                                {"t": "2026-07-12T00:00:00+00:00", "value": 2}
                            ],
                        }
                    ],
                },
            }
        },
        "snapshot_schemas": {},
        "snapshots": [],
    }

    apply_presentation_contract(content, artifact)

    series = artifact["items"]["snapshot_charts_db.database_temp_files_delta"]["result"]["series"][0]
    assert series["semantic_role"] == "counter_delta"
    assert series["value_kind"] == "integer"
    assert series["encoding"] == "decimal_string"
    assert series["points"][0]["value"] == "2"


def test_host_source_timeouts_do_not_exceed_one_second(content_path: Path) -> None:
    content = load_content(content_path)
    max_timeout_ms = int(HOST_COMMAND_TIMEOUT_SECONDS * 1000)

    assert content.report["runtime_policy"]["default_shell_timeout_ms"] == max_timeout_ms
    for script_id, source in content.scripts.items():
        timeout_ms = source.get(
            "timeout_ms",
            content.report["runtime_policy"]["default_shell_timeout_ms"],
        )
        assert 0 < timeout_ms <= max_timeout_ms, script_id
    for source_id, source in content.pythons.items():
        if source["local_only"]:
            assert 0 < source["timeout_ms"] <= max_timeout_ms, source_id

    assert content.pythons["security.role_password_hashes"]["timeout_ms"] == 5000


def test_os_capacity_scripts_emit_canonical_structured_values(content_path: Path) -> None:
    content = load_content(content_path)
    for script_id in (
        "os.disk_usage",
        "os.memory_info",
        "os.huge_page_pools",
        "os.total_ram",
    ):
        assert content.scripts[script_id]["output"] == "table_json"
        script = content.path / "scripts" / content.scripts[script_id]["script_file"]
        completed = subprocess.run(
            ["/bin/sh", str(script)],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        rows = json.loads(completed.stdout)
        assert isinstance(rows, list) and rows, script_id

    disk_rows = json.loads(
        subprocess.run(
            ["/bin/sh", str(content.path / "scripts/os/df_h.sh")],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout
    )
    assert all(
        isinstance(row[key], int)
        for row in disk_rows
        for key in ("total_bytes", "used_bytes", "available_bytes", "used_pct")
    )

    pool_rows = json.loads(
        subprocess.run(
            ["/bin/sh", str(content.path / "scripts/os/huge_page_pools.sh")],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout
    )
    assert [row["page_size_bytes"] for row in pool_rows] == sorted(
        row["page_size_bytes"] for row in pool_rows
    )
    assert all(
        set(row)
        == set(
            content.presentation_catalog["presentation_catalog"]["source_overrides"][
                "os.huge_page_pools"
            ]
        )
        for row in pool_rows
    )
    assert all(
        isinstance(row[key], int)
        for row in pool_rows
        for key in (
            "page_size_bytes",
            "total_pages",
            "used_pages",
            "free_pages",
            "reserved_pages",
            "free_unreserved_pages",
            "surplus_pages",
            "pool_total_bytes",
            "pool_used_bytes",
            "pool_reserved_bytes",
            "pool_free_unreserved_bytes",
            "numa_nodes_with_pages",
        )
    )

    volume_text = (content.path / "scripts/os/lshw_volume.sh").read_text(encoding="utf-8")
    assert "fsuse_pct" in volume_text
    assert "fsuse%" in volume_text


def test_sql_sources_do_not_apply_presentation_formatting(content_path: Path) -> None:
    for sql_path in (content_path / "queries").rglob("*.sql"):
        sql = sql_path.read_text(encoding="utf-8")
        assert re.search(r"\bround\s*\(", sql, re.IGNORECASE) is None, sql_path
        assert "pg_size_pretty" not in sql.lower(), sql_path
        assert "time_since_reset" not in sql, sql_path


def test_version_optional_metric_counters_are_null_not_zero(content_path: Path) -> None:
    metric_sql = {
        path.relative_to(content_path).as_posix(): path.read_text(encoding="utf-8")
        for path in (content_path / "queries" / "metrics").glob("*.sql")
    }
    for path, sql in metric_sql.items():
        assert re.search(r"\b0::[a-z0-9_ ]+\s+as\s+", sql, re.IGNORECASE) is None, path

    content = load_content(content_path)
    checkpointer = content.queries["metrics.checkpointer_delta"]["variants"]
    assert set(checkpointer[0]["column_statuses"]) == {
        "restartpoints_timed",
        "restartpoints_requested",
        "restartpoints_done",
        "slru_written",
    }
    assert set(checkpointer[1]["column_statuses"]) == {"slru_written"}

    maintenance = content.queries["metrics.objects_table_maintenance_delta"]["variants"]
    assert maintenance[0]["max_pg_version"] == 179999
    assert set(maintenance[0]["column_statuses"]) == {
        "vacuum_time_ms",
        "autovacuum_time_ms",
        "analyze_time_ms",
        "autoanalyze_time_ms",
        "maintenance_time_ms",
    }

    conflicts = content.queries["metrics.recovery_conflicts_delta"]["variants"]
    assert conflicts[0]["max_pg_version"] == 159999
    assert set(conflicts[0]["column_statuses"]) == {"confl_active_logicalslot"}


def test_validator_rejects_host_source_timeouts_over_one_second(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    report = deepcopy(content.report)
    scripts = deepcopy(content.scripts)
    pythons = deepcopy(content.pythons)
    report["runtime_policy"]["default_shell_timeout_ms"] = 1001
    scripts["os.kernel_version"]["timeout_ms"] = 1001
    pythons["security.pgdata_permissions"]["timeout_ms"] = 1001
    invalid = replace(content, report=report, scripts=scripts, pythons=pythons)

    issues = validate_content(invalid)

    messages = {(issue.location, issue.message) for issue in issues}
    assert ("report.yaml", "runtime_policy.default_shell_timeout_ms must not exceed 1000") in messages
    assert ("script:os.kernel_version", "timeout_ms must not exceed 1000 for host shell scripts") in messages
    assert ("python:security.pgdata_permissions", "local_only timeout_ms must not exceed 1000") in messages


def test_content_pack_exposes_one_effective_document_with_file_provenance(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    document = content.document

    assert document["report"] == content.report["report"]
    assert document["sections"] == content.report["sections"]
    assert document["queries"] == content.queries
    assert document["scripts"] == content.scripts
    assert document["metrics"] == content.metrics
    assert document["python_sources"] == content.pythons
    assert document["sampler_providers"] == content.sampler_providers
    assert document["field_reference"]["sections/*/items/*/render"]
    assert content.provenance["sections"] == ["report.yaml"]
    assert content.provenance["queries/indexes.redundant_indexes"] == [
        "queries.yaml",
        "catalog/dba_extra.yaml",
    ]

    source_roots = {
        "query": "queries",
        "script": "scripts",
        "metric": "metrics",
        "python": "python_sources",
    }
    for _section_id, _item_key, item_id, item in iter_report_items(content):
        source_kind = next(iter({"query", "script", "metric", "python"}.intersection(item)))
        assert item[source_kind] in document[source_roots[source_kind]], item_id

    artifact = create_artifact(
        content,
        build_plan(content, 180000, mode=ONE_SHOT_MODE),
        {},
        "2026-07-11T00:00:00+00:00",
    )
    assert artifact["content"]["document"]["queries"] == content.queries
    assert artifact["content"]["provenance"] == content.provenance


def test_content_contract_has_no_legacy_report_state(content_path: Path) -> None:
    content = load_content(content_path)

    assert "default_state" not in content.report["report"]
    assert content.report["defaults"]["item"]["state"] == "collapsed"
    assert content.report["defaults"]["section"]["state"] == "expanded"


def test_each_report_section_expands_three_to_five_items(content_path: Path) -> None:
    content = load_content(content_path)
    default_state = content.report["defaults"]["item"]["state"]

    for section_id, section in content.report["sections"].items():
        expanded = [
            item_key
            for item_key, item in section["items"].items()
            if item.get("state", default_state) == "expanded"
        ]
        assert 3 <= len(expanded) <= 5, (section_id, expanded)


def test_field_reference_covers_every_unified_content_node(content_path: Path) -> None:
    content = load_content(content_path)
    reference = content.document["field_reference"]
    patterns = [path.split("/") for path in reference if path != "*"]
    missing: set[str] = set()

    def covered(path: list[str]) -> bool:
        return any(
            len(pattern) == len(path)
            and all(expected == "*" or expected == actual for expected, actual in zip(pattern, path))
            for pattern in patterns
        )

    def visit(value: object, path: list[str]) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = [*path, str(key)]
                if not covered(child_path):
                    missing.add("/".join(child_path))
                visit(child, child_path)
        elif isinstance(value, list):
            list_path = [*path[:-1], path[-1] + "[]"]
            if not covered(list_path):
                missing.add("/".join(list_path))
            for child in value:
                visit(child, list_path)

    for root, value in content.document.items():
        if root == "field_reference":
            continue
        if not covered([root]):
            missing.add(root)
        visit(value, [root])

    assert not missing


def test_validator_rejects_missing_or_catch_all_field_help(content_path: Path) -> None:
    content = load_content(content_path)
    reference_catalog = deepcopy(content.field_reference_catalog)
    fields = reference_catalog["field_reference"]["fields"]
    del fields["report/id"]
    fields["*"] = "Generic help is not allowed."
    document = deepcopy(content.document)
    document["field_reference"] = deepcopy(fields)
    invalid = replace(
        content,
        field_reference_catalog=reference_catalog,
        document=document,
    )

    issues = validate_content(invalid)
    messages = [issue.message for issue in issues if issue.code == "field_reference"]

    assert any("must not contain a catch-all" in message for message in messages)
    assert any("report/id" in message for message in messages)


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
        allowed_tags = set(content.report["report"]["allowed_item_tags"])
        assert set(tags).issubset(allowed_tags), item_id


def test_report_items_have_markdown_instructions(content_path: Path) -> None:
    content = load_content(content_path)
    item_ids = []
    item_links = re.compile(
        r"\[([a-z][a-z0-9_.-]*)\]\(#item-([a-z][a-z0-9_.-]*)\)"
    )
    related_item_line = re.compile(
        r"- \[([a-z][a-z0-9_.-]*)\]\(#item-\1\) — \S.*"
    )
    required_headings = (
        "## What this item shows",
        "## What to watch",
        "## Common fault causes",
        "## Automatic evaluation",
        "## Checklist",
    )
    instructions_without_related_items = set()
    for _section_id, _item_key, item_id, _item in iter_report_items(content):
        item_ids.append(item_id)
        instruction = content.instructions.get(item_id)
        assert instruction, item_id
        assert instruction["format"] == "markdown"
        assert instruction["path"].endswith(".md")
        text = instruction["text"]
        assert re.match(r"^# [^#\s].*", text), item_id
        assert f"This instruction belongs to report item `{item_id}`." in text
        for heading in required_headings:
            assert text.splitlines().count(heading) == 1, (item_id, heading)

        links = item_links.findall(text)
        targets = [target for _label, target in links]
        assert all(label == target for label, target in links), item_id
        assert item_id not in targets
        assert len(targets) == len(set(targets)), item_id
        if "## Related report items" in text:
            assert targets, item_id
            lines = text.splitlines()
            related_start = lines.index("## Related report items") + 1
            related_end = next(
                (
                    index
                    for index in range(related_start, len(lines))
                    if lines[index].startswith("## ")
                ),
                len(lines),
            )
            related_lines = [line for line in lines[related_start:related_end] if line.strip()]
            assert all(related_item_line.fullmatch(line) for line in related_lines), item_id
        else:
            instructions_without_related_items.add(item_id)
    assert set(content.instructions) == set(item_ids)
    assert all(
        target in item_ids
        for instruction in content.instructions.values()
        for _label, target in item_links.findall(instruction["text"])
    )
    assert instructions_without_related_items == {
        "os.lshw_display",
        "os.lshw_input",
        "os.lshw_multimedia",
    }


def test_overview_instructions_have_interpretation_sections(content_path: Path) -> None:
    content = load_content(content_path)
    overview_item_ids = [
        item_id
        for section_id, _item_key, item_id, _item in iter_report_items(content)
        if section_id == "overview"
    ]
    assert len(overview_item_ids) == 14
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
    assert len(os_item_ids) == 49
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
    assert "limit 1000" in lock_waits_sql
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
    assert len(item_ids) == 8
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
            if int(variant.get("max_pg_version", 999999)) < 140000:
                assert "null::boolean as toplevel" in sql, query_id
            else:
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
        "statements.temp_io_delta",
        "statements.planning_delta",
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
            if int(variant.get("max_pg_version", 999999)) < 140000:
                assert "false::boolean as toplevel" in sql, metric_id
            else:
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

    assert len(item_ids) == 30
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


def test_new_delta_items_keep_scope_notation_contract(content_path: Path) -> None:
    content = load_content(content_path)
    new_metric_ids = {
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

    for metric_id in new_metric_ids:
        metric = content.metrics[metric_id]
        assert metric["title"].endswith("Delta"), metric_id
        assert metric["database_scope"] in {"all_databases", "current_database"}, metric_id
        source = content.queries[metric["source_query"]]
        assert source["database_scope"] == metric["database_scope"], metric_id


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
        "statements.temp_io_delta": (
            ["dimensions.database_id", "dimensions.user_id", "dimensions.query_id", "dimensions.toplevel"],
            50,
        ),
        "io.activity_delta": (
            ["dimensions.backend_type", "dimensions.object", "dimensions.context"],
            None,
        ),
        "checkpoints.checkpointer_delta": (["dimensions.scope"], None),
        "wal.activity_delta": (["dimensions.scope"], None),
        "objects.table_maintenance_delta": (
            ["dimensions.database_id", "dimensions.relation_id"],
            200,
        ),
        "replication.recovery_conflicts_delta": (["dimensions.database_id"], None),
        "database.session_outcomes_delta": (["dimensions.database_id"], None),
        "replication.physical_progress_delta": (["dimensions.sender_pid"], 50),
        "statements.planning_delta": (
            ["dimensions.database_id", "dimensions.user_id", "dimensions.query_id", "dimensions.toplevel"],
            50,
        ),
        "checkpoints.bgwriter_delta": (["dimensions.scope"], None),
        "slru.activity_delta": (["dimensions.name"], None),
        "wal.archiver_delta": (["dimensions.scope"], None),
        "replication.logical_slot_delta": (["dimensions.slot_name"], 50),
        "replication.subscription_errors_delta": (["dimensions.subscription_id"], 50),
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
        "statements.temp_io_delta",
        "statements.planning_delta",
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
    assert "commit_delta_raw" not in database_columns
    assert "pg_diag_commit_overhead" not in database_columns
    assert database_columns["commit_delta"]["transform"] == "delta"
    assert database_columns["commits_per_sec"]["transform"] == "rate"
    assert database_metric["table"]["drop_zero_rows"] is False
    assert database_metric["evaluation"]["rules"][0]["severity"] == "medium"
    assert content.metrics["objects.table_scan_delta"]["evaluation"]["rules"][0][
        "severity"
    ] == "medium"


def test_database_scope_contract_matches_queries_and_actual_sql(content_path: Path) -> None:
    content = load_content(content_path)

    for metric_id, metric in content.metrics.items():
        if metric.get("database_scope") is None:
            continue
        source = content.queries[metric["source_query"]]
        assert source.get("database_scope") == metric["database_scope"], metric_id

    all_database_sources = {
        "database.database_stats",
        "metrics.database_transaction_rate",
        "metrics.database_tuple_dml_rate",
        "metrics.database_tuple_access_rate",
        "metrics.database_block_access_rate",
        "metrics.database_temp_files_delta",
        "metrics.database_temp_bytes_rate",
        "metrics.database_io_time_rate",
        "metrics.database_backends",
        "metrics.database_deadlocks",
        "metrics.database_workload_delta",
    }
    for source_id in all_database_sources:
        source = content.queries[source_id]
        assert source["database_scope"] == "all_databases"
        for variant in source["variants"]:
            sql = (content.path / "queries" / variant["sql_file"]).read_text(
                encoding="utf-8"
            ).lower()
            assert "where datname is not null" in sql, source_id
            assert "where datname = current_database()" not in sql, source_id

    database_stats_source = content.queries["database.database_stats"]
    assert database_stats_source["title"] == "Database Statistics"
    for variant in database_stats_source["variants"]:
        sql = (content.path / "queries" / variant["sql_file"]).read_text(
            encoding="utf-8"
        ).lower()
        assert "current_database()" not in sql
        assert "from pg_index" not in sql
        assert "datid" in sql
        assert "stats_reset" in sql
        assert "sys_id" not in sql
        assert "pg_control_system" not in sql

    assert content.metrics["database.workload_delta"]["database_scope"] == "all_databases"
    assert content.metrics["statements.total_time_delta"]["database_scope"] == (
        "current_database"
    )
    assert content.queries["statements.top_by_total_time"]["database_scope"] == (
        "current_database"
    )

    for source_id in ("activity.session_states", "metrics.activity_sessions_by_state"):
        source = content.queries[source_id]
        assert source["database_scope"] == "all_databases"
        for variant in source["variants"]:
            sql = (content.path / "queries" / variant["sql_file"]).read_text(
                encoding="utf-8"
            ).lower()
            assert "current_database()" not in sql, source_id
            assert "datallowconn" not in sql, source_id


def test_validator_rejects_invalid_or_mismatched_database_scope(content_path: Path) -> None:
    content = load_content(content_path)
    content.queries["metrics.database_transaction_rate"]["database_scope"] = "cluster"

    issues = validate_content(content)

    assert any(
        issue.code == "database_scope"
        and issue.location == "query:metrics.database_transaction_rate"
        for issue in issues
    )
    assert any(
        issue.code == "database_scope"
        and issue.location == "metric:database.transaction_rate"
        and "must match source query" in issue.message
        for issue in issues
    )


def test_every_non_os_item_resolves_database_scope(content_path: Path) -> None:
    content = load_content(content_path)
    overview_items = list(content.report["sections"]["overview"]["items"])
    assert overview_items.index("database_volume") == overview_items.index("server_version") + 1
    assert overview_items.index("pg_config") == overview_items.index("database_volume") + 1
    assert overview_items.index("pg_controldata") == overview_items.index("pg_config") + 1
    plan = build_plan(
        content,
        180000,
        mode=SNAPSHOTS_MODE,
        collection_mode="local",
    )
    os_sections = {"os", "snapshot_charts_os"}

    for item in plan.items:
        scope = item.source_metadata.get("database_scope")
        if item.section_id in os_sections:
            assert scope is None, item.item_id
        else:
            assert scope in {"all_databases", "current_database"}, item.item_id

    by_id = {item.item_id: item for item in plan.items}
    assert by_id["overview.server_version"].source_metadata["database_scope"] == (
        "all_databases"
    )
    assert by_id["activity_locks.connection_pressure"].source_metadata[
        "database_scope"
    ] == "all_databases"
    assert by_id["overview.pg_config"].source_metadata["database_scope"] == "all_databases"
    assert by_id["overview.pg_config"].source_kind == "script"
    assert by_id["overview.pg_controldata"].source_metadata["database_scope"] == "all_databases"
    assert by_id["overview.pg_controldata"].source_kind == "python"
    assert by_id["overview.database_volume"].source_metadata["database_scope"] == "all_databases"
    assert by_id["overview.database_volume"].source_kind == "python"
    assert all(
        item.source_metadata["database_scope"] == "current_database"
        for item in plan.items
        if item.section_id in {"sql_workload", "object_workload", "indexes"}
    )


def test_validator_rejects_invalid_scope_defaults_and_section_switch(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    content.report["defaults"]["item"]["database_scope"] = "cluster"
    content.report["sections"]["os"]["show_database_scope"] = "no"

    issues = validate_content(content)

    assert any(
        issue.code == "database_scope"
        and issue.location == "report.yaml:defaults.item"
        for issue in issues
    )
    assert any(
        issue.code == "database_scope"
        and issue.location == "report.yaml:sections.os"
        and "must be boolean" in issue.message
        for issue in issues
    )


@pytest.mark.parametrize("section_id, expected_count", [("replication", 8), ("wal_io_checkpoints", 7)])
def test_replication_and_wal_instructions_define_complete_interpretation_contract(
    content_path: Path,
    section_id: str,
    expected_count: int,
) -> None:
    content = load_content(content_path)
    item_ids = [
        item_id
        for current_section, _item_key, item_id, _item in iter_report_items(content)
        if current_section == section_id
    ]

    assert len(item_ids) == expected_count
    for item_id in item_ids:
        text = content.instructions[item_id]["text"]
        assert "This instruction belongs to" in text, item_id
        assert "## What to watch" in text, item_id
        assert "## Automatic evaluation" in text, item_id
        assert "## Common fault causes" in text, item_id


def test_replication_queries_preserve_lsn_and_lag_semantics(content_path: Path) -> None:
    content = load_content(content_path)
    query_root = content.path / "queries"
    physical_sql = (query_root / "replication/physical_replication.sql").read_text(
        encoding="utf-8"
    ).lower()
    receiver_sql = (query_root / "replication/wal_receiver.sql").read_text(
        encoding="utf-8"
    ).lower()

    assert "extract(epoch from" in physical_sql
    assert "extract(seconds from" not in physical_sql
    assert " % " not in physical_sql
    assert "sent_lsn::text" in physical_sql
    assert "current_to_replay_lag_bytes" in physical_sql
    assert "state" in physical_sql and "sync_state" in physical_sql

    assert " % " not in receiver_sql
    assert "flushed_lsn::text" in receiver_sql
    assert "sender_host" in receiver_sql
    assert "pg_wal_lsn_diff(latest_end_lsn, flushed_lsn)" in receiver_sql

    roles_sql = (query_root / "security/replication_roles.sql").read_text(
        encoding="utf-8"
    ).lower()
    assert "oid as role_oid" in roles_sql
    assert "when oid = 10 then 'ok'" in roles_sql


def test_subscription_workers_cover_pg14_through_pg18_without_fake_apply_lag(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    query = content.queries["replication.subscription_workers"]
    pg14 = select_query_variant("replication.subscription_workers", query, 140000)
    pg15 = select_query_variant("replication.subscription_workers", query, 150000)
    pg16 = select_query_variant("replication.subscription_workers", query, 160000)
    pg17 = select_query_variant("replication.subscription_workers", query, 170000)
    pg18 = select_query_variant("replication.subscription_workers", query, 180000)

    assert pg14.variant["sql_file"].endswith("subscription_workers_pg14.sql")
    assert pg15.variant["sql_file"].endswith("subscription_workers_pg15.sql")
    assert pg16.variant["sql_file"].endswith("subscription_workers_pg16.sql")
    assert pg17.variant["sql_file"].endswith("subscription_workers_pg17.sql")
    assert pg18.variant["sql_file"].endswith("subscription_workers_pg18.sql")
    assert "leader_pid" in pg14.variant["column_statuses"]
    assert "leader_pid" in pg15.variant["column_statuses"]
    assert "leader_pid" not in pg16.variant.get("column_statuses", {})
    assert "conflict_count" in pg17.variant["column_statuses"]
    assert "conflict_count" not in pg18.variant.get("column_statuses", {})

    pg14_sql = (content.path / "queries" / pg14.variant["sql_file"]).read_text(
        encoding="utf-8"
    ).lower()
    pg15_sql = (content.path / "queries" / pg15.variant["sql_file"]).read_text(
        encoding="utf-8"
    ).lower()
    pg16_sql = (content.path / "queries" / pg16.variant["sql_file"]).read_text(
        encoding="utf-8"
    ).lower()
    pg17_sql = (content.path / "queries" / pg17.variant["sql_file"]).read_text(
        encoding="utf-8"
    ).lower()
    pg18_sql = (content.path / "queries" / pg18.variant["sql_file"]).read_text(
        encoding="utf-8"
    ).lower()
    for sql in (pg14_sql, pg15_sql, pg16_sql, pg17_sql, pg18_sql):
        assert "pg_wal_lsn_diff(latest_end_lsn, received_lsn)" in sql
        assert "publisher_receive_lag_bytes" in sql
        assert "receive_apply_lag_bytes" not in sql
        assert "from pg_catalog.pg_subscription s" in sql
        assert "left join pg_catalog.pg_stat_subscription w" in sql
        assert "to_jsonb" not in sql
    assert "pg_stat_subscription_stats" not in pg14_sql
    assert "pg_stat_subscription_stats" in pg15_sql
    assert "w.leader_pid" not in pg15_sql
    assert "w.leader_pid" in pg16_sql
    assert "w.worker_type" in pg17_sql
    assert "confl_insert_exists" not in pg17_sql
    assert "confl_insert_exists" in pg18_sql


def test_replication_slot_variants_match_versioned_view_columns(content_path: Path) -> None:
    content = load_content(content_path)
    query = content.queries["replication.slots"]
    pg15 = select_query_variant("replication.slots", query, 150000)
    pg16 = select_query_variant("replication.slots", query, 160000)
    pg17 = select_query_variant("replication.slots", query, 170000)

    assert pg15.variant["sql_file"].endswith("replication_slots_pg14_pg15.sql")
    assert pg16.variant["sql_file"].endswith("replication_slots_pg16.sql")
    assert pg17.variant["sql_file"].endswith("replication_slots_pg17_plus.sql")
    assert set(pg15.variant["column_statuses"]) == {
        "inactive_since", "invalidation_reason", "failover", "synced", "conflicting"
    }
    assert set(pg16.variant["column_statuses"]) == {
        "inactive_since", "invalidation_reason", "failover", "synced"
    }
    assert not pg17.variant.get("column_statuses")

    for selected in (pg15, pg16, pg17):
        sql = (content.path / "queries" / selected.variant["sql_file"]).read_text(
            encoding="utf-8"
        ).lower()
        assert "to_jsonb" not in sql
        assert "retained_wal_bytes" in sql


def test_subscription_delta_does_not_fabricate_pre_pg18_conflicts(content_path: Path) -> None:
    content = load_content(content_path)
    query = content.queries["metrics.subscription_errors_delta"]
    pg17 = select_query_variant("metrics.subscription_errors_delta", query, 170000)
    pg18 = select_query_variant("metrics.subscription_errors_delta", query, 180000)

    assert "conflict_count" in pg17.variant["column_statuses"]
    assert "conflict_count" not in pg18.variant.get("column_statuses", {})
    pg17_sql = (content.path / "queries" / pg17.variant["sql_file"]).read_text(
        encoding="utf-8"
    ).lower()
    pg18_sql = (content.path / "queries" / pg18.variant["sql_file"]).read_text(
        encoding="utf-8"
    ).lower()
    assert "null::int8 as conflict_count" in pg17_sql
    assert "coalesce" not in pg17_sql
    assert "confl_insert_exists" in pg18_sql
    assert "errors_total" not in pg17_sql
    assert "errors_total" not in pg18_sql


def test_wal_archiver_uses_real_segment_size_and_timeline_guard(content_path: Path) -> None:
    content = load_content(content_path)
    sql = (content.path / "queries/wal/archiver.sql").read_text(encoding="utf-8").lower()

    assert "pg_size_bytes(current_setting('wal_segment_size'))" in sql
    assert "4294967296::bigint / wal_segment_size_bytes" in sql
    assert "segments_ahead_of_last_archived_same_timeline" in sql
    assert "substr(current_wal_file, 1, 8) = substr(last_archived_wal, 1, 8)" in sql
    assert "* 256" not in sql
    assert "pending_wal_count" not in sql
    assert "when not pg_catalog.pg_is_in_recovery()" in sql


def test_wal_position_and_checkpointer_are_role_and_version_aware(content_path: Path) -> None:
    content = load_content(content_path)
    wal_position = (content.path / "queries/wal/wal_position_pg14.sql").read_text(
        encoding="utf-8"
    ).lower()
    assert "pg_current_wal_insert_lsn" in wal_position
    assert "pg_current_wal_flush_lsn" in wal_position
    assert "pg_last_wal_receive_lsn" in wal_position
    assert "pg_last_wal_replay_lsn" in wal_position
    assert "pg_control_checkpoint" in wal_position

    query = content.queries["checkpoints.checkpointer"]
    pg17 = select_query_variant("checkpoints.checkpointer", query, 170000)
    pg18 = select_query_variant("checkpoints.checkpointer", query, 180000)
    pg17_sql = (content.path / "queries" / pg17.variant["sql_file"]).read_text(
        encoding="utf-8"
    ).lower()
    pg18_sql = (content.path / "queries" / pg18.variant["sql_file"]).read_text(
        encoding="utf-8"
    ).lower()
    assert "num_done" not in pg17_sql
    assert "slru_written" not in pg17_sql
    assert "num_done" in pg18_sql
    assert "slru_written" in pg18_sql


def test_pg_stat_io_keeps_dimensions_and_unknown_pg18_writeback_bytes(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    query = content.queries["io.pg_stat_io"]
    for variant in query["variants"]:
        sql = (content.path / "queries" / variant["sql_file"]).read_text(
            encoding="utf-8"
        ).lower()
        assert "group by backend_type, object, context" in sql
        assert "rollup" not in sql
        assert "backend_type = 'client backend' and object = 'relation'" in sql
    pg18 = select_query_variant("io.pg_stat_io", query, 180000)
    pg18_sql = (content.path / "queries" / pg18.variant["sql_file"]).read_text(
        encoding="utf-8"
    ).lower()
    assert "null::numeric as writeback_bytes" in pg18_sql
    assert "0::int8 as writeback_bytes" not in pg18_sql
    assert "_bytes_mb" not in pg18_sql


def test_replication_and_wal_sources_never_reset_statistics(content_path: Path) -> None:
    content = load_content(content_path)
    item_ids = {
        item_id
        for section_id, _item_key, item_id, _item in iter_report_items(content)
        if section_id in {"replication", "wal_io_checkpoints"}
    }
    source_ids = {
        item["query"]
        for section_id, _item_key, item_id, item in iter_report_items(content)
        if item_id in item_ids
    }
    for source_id in source_ids:
        for variant in content.queries[source_id]["variants"]:
            sql = (content.path / "queries" / variant["sql_file"]).read_text(
                encoding="utf-8"
            ).lower()
            assert not re.search(r"\bpg_(?:stat_)?reset\w*\s*\(", sql), source_id


def test_maintenance_progress_defines_point_in_time_interpretation_contract(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    items = [
        (item_id, item)
        for section_id, _item_key, item_id, item in iter_report_items(content)
        if section_id == "maintenance_progress"
    ]

    assert len(items) == 4
    for item_id, item in items:
        text = content.instructions[item_id]["text"]
        assert "This instruction belongs to" in text, item_id
        assert "## What to watch" in text, item_id
        assert "## Automatic evaluation" in text, item_id
        assert "## Common fault causes" in text, item_id
        assert "one-time" in text.lower(), item_id

        query = content.queries[item["query"]]
        assert query["collection"] == {"default": "once", "supports": ["once"]}

    plan = build_plan(content, 180000, mode=SNAPSHOTS_MODE)
    by_id = {planned.item_id: planned for planned in plan.items}
    for item_id, _item in items:
        assert by_id[item_id].collection_scope == "once"


def test_maintenance_progress_queries_use_current_database_oid_scope_and_command_age(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    source_ids = {
        "progress.vacuum",
        "progress.create_index",
        "progress.cluster",
        "progress.copy",
    }
    for source_id in source_ids:
        query = content.queries[source_id]
        for variant in query["variants"]:
            sql = (content.path / "queries" / variant["sql_file"]).read_text(
                encoding="utf-8"
            ).lower()
            assert "p.datid" in sql, source_id
            assert "where p.datid =" in sql, source_id
            assert "pg_database" in sql, source_id
            assert "a.query_start" in sql, source_id
            assert "query_age_seconds" in sql, source_id
            assert "xact_age_seconds" not in sql, source_id


def test_vacuum_progress_uses_query_evidence_and_version_specific_units(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    query = content.queries["progress.vacuum"]
    pg16 = select_query_variant("progress.vacuum", query, 160000)
    pg17 = select_query_variant("progress.vacuum", query, 170000)
    pg16_sql = (content.path / "queries" / pg16.variant["sql_file"]).read_text(
        encoding="utf-8"
    ).lower()
    pg17_sql = (content.path / "queries" / pg17.variant["sql_file"]).read_text(
        encoding="utf-8"
    ).lower()

    for sql in (pg16_sql, pg17_sql):
        assert "backend_xid" not in sql
        assert "to prevent wraparound" in sql
        assert "anti_wraparound" in sql
        assert "a.backend_type" in sql
    assert "max_dead_tuples" in pg16_sql
    assert "num_dead_tuples" in pg16_sql
    assert "max_dead_tuple_bytes" not in pg16_sql
    assert "max_dead_tuple_bytes" in pg17_sql
    assert "dead_tuple_bytes" in pg17_sql
    assert "num_dead_item_ids" in pg17_sql
    assert "indexes_total" in pg17_sql
    assert "indexes_processed" in pg17_sql


def test_copy_progress_never_hides_locked_rows_or_takes_relation_size_lock(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    variant = content.queries["progress.copy"]["variants"][0]
    sql = (content.path / "queries" / variant["sql_file"]).read_text(
        encoding="utf-8"
    ).lower()

    assert "pg_relation_size" not in sql
    assert "pg_locks" not in sql
    assert "accessexclusivelock" not in sql
    assert "tuples_skipped" in sql
    assert "to_jsonb(p)" in sql
    assert "case when p.relid <> 0" in sql


def test_index_and_cluster_progress_expose_command_and_stable_oids(content_path: Path) -> None:
    content = load_content(content_path)
    for source_id in ("progress.create_index", "progress.cluster"):
        variant = content.queries[source_id]["variants"][0]
        sql = (content.path / "queries" / variant["sql_file"]).read_text(
            encoding="utf-8"
        ).lower()
        assert "p.command" in sql
        assert "p.relid" in sql
        assert "::regclass::text" in sql
    cluster_sql = (content.path / "queries/progress/cluster_progress.sql").read_text(
        encoding="utf-8"
    ).lower()
    assert "p.index_rebuild_count" in cluster_sql


def test_storage_vacuum_defines_complete_once_contract(content_path: Path) -> None:
    content = load_content(content_path)
    items = [
        (item_id, item)
        for section_id, _key, item_id, item in iter_report_items(content)
        if section_id == "storage_vacuum"
    ]
    assert len(items) == 8
    for item_id, item in items:
        text = content.instructions[item_id]["text"]
        assert "This instruction belongs to" in text, item_id
        assert "## What to watch" in text, item_id
        assert "## Automatic evaluation" in text, item_id
        assert "## Common fault causes" in text, item_id
        assert content.queries[item["query"]]["collection"] == {
            "default": "once",
            "supports": ["once"],
        }


def test_autovacuum_queue_covers_all_vacuum_triggers_and_remains_bounded(
    content_path: Path,
) -> None:
    sql = (content_path / "queries/vacuum/autovacuum_queue.sql").read_text(
        encoding="utf-8"
    ).lower()
    for token in (
        "autovacuum_vacuum_max_threshold",
        "autovacuum_vacuum_insert_threshold",
        "autovacuum_vacuum_insert_scale_factor",
        "n_ins_since_vacuum",
        "relfrozenxid",
        "relminmxid",
        "autovacuum_enabled",
        "vacuum_in_progress",
    ):
        assert token in sql
    assert "limit 200" in sql
    assert "pg_diag_internal_severity" in sql


def test_sequence_exhaustion_handles_direction_cycle_and_visibility(content_path: Path) -> None:
    sql = (content_path / "queries/storage/sequence_status.sql").read_text(
        encoding="utf-8"
    ).lower()
    assert "when sc.increment_by > 0" in sql
    assert "sc.max_value - sc.last_value" in sql
    assert "when cycle or values_consumed is null then null" in sql
    assert "cache_size" in sql
    assert "data_type" in sql
    assert "last_value is not null as value_visible" in sql
    assert "limit 200" in sql


def test_table_size_detail_bounds_expensive_size_calls_before_collection(
    content_path: Path,
) -> None:
    sql = (content_path / "queries/storage/table_size_detailed.sql").read_text(
        encoding="utf-8"
    ).lower()
    candidate_end = sql.index("),\nsizes as")
    assert "relpages" in sql[:candidate_end]
    assert "limit 200" in sql[:candidate_end]
    assert "pg_total_relation_size" not in sql[:candidate_end]
    assert "pg_total_relation_size" in sql[candidate_end:]
    assert "limit 100" in sql[candidate_end:]
    assert "$other$" not in sql


def test_xmin_horizon_includes_non_client_backends_and_concrete_pid(
    content_path: Path,
) -> None:
    summary_sql = (content_path / "queries/vacuum/xmin_horizon.sql").read_text(
        encoding="utf-8"
    ).lower()
    blocker_sql = (content_path / "queries/vacuum/xmin_horizon_blockers.sql").read_text(
        encoding="utf-8"
    ).lower()
    assert "backend_type = 'client backend'" not in summary_sql
    assert "backend_type <> 'walsender'" in summary_sql
    assert "backend_type = 'client backend'" not in blocker_sql
    assert "blocker_pid" in blocker_sql
    assert "blocker_backend_type" in blocker_sql


def test_storage_wraparound_and_checksum_outputs_support_findings(content_path: Path) -> None:
    wrap_sql = (content_path / "queries/vacuum/database_wraparound.sql").read_text(
        encoding="utf-8"
    ).lower()
    checksum_sql = (content_path / "queries/security/data_checksums.sql").read_text(
        encoding="utf-8"
    ).lower()
    assert "vacuum_failsafe_age" in wrap_sql
    assert "vacuum_multixact_failsafe_age" in wrap_sql
    assert "pg_diag_internal_severity" in wrap_sql
    assert "checksum_last_failure as last_failure" in checksum_sql


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


def test_host_items_have_unique_self_contained_posix_scripts(content_path: Path) -> None:
    content = load_content(content_path)
    script_files = [manifest["script_file"] for manifest in content.scripts.values()]
    assert len(script_files) == len(set(script_files))

    for script_id, manifest in content.scripts.items():
        script = (content.path / "scripts" / manifest["script_file"]).read_text(
            encoding="utf-8"
        )
        assert script.startswith("#!/bin/sh\n"), script_id
        assert 'dirname "$0"' not in script, script_id
        assert "python" not in script.lower(), script_id
        syntax = subprocess.run(
            ("/bin/sh", "-n", str(content.path / "scripts" / manifest["script_file"])),
            capture_output=True,
            text=True,
            check=False,
        )
        assert syntax.returncode == 0, f"{script_id}: {syntax.stderr}"


def test_huge_page_items_are_independent_one_shot_sources(content_path: Path) -> None:
    content = load_content(content_path)
    plan = build_plan(content, 180000, mode=SNAPSHOTS_MODE)
    by_id = {item.item_id: item for item in plan.items}

    diagnostic = by_id["os.postgresql_huge_pages"]
    pools = by_id["os.huge_page_pools"]
    assert diagnostic.source_kind == "python"
    assert diagnostic.source_id == "os.postgresql_huge_pages"
    assert diagnostic.python_file == "os/postgresql_huge_pages.py"
    assert diagnostic.collection_scope == "once"
    assert pools.source_kind == "script"
    assert pools.source_id == "os.huge_page_pools"
    assert pools.script_file == "os/huge_page_pools.sh"
    assert pools.collection_scope == "once"
    assert content.pythons[diagnostic.source_id]["local_only"] is True
    assert content.scripts[pools.source_id]["local_only"] is True

    diagnostic_text = (content.path / "python" / diagnostic.python_file).read_text(
        encoding="utf-8"
    )
    pools_text = (content.path / "scripts" / pools.script_file).read_text(
        encoding="utf-8"
    )
    assert "sys_memory_total" not in diagnostic_text
    assert "huge_page_pools.sh" not in diagnostic_text
    assert "postgresql_huge_pages.py" not in pools_text
    assert "sys_memory_total" not in pools_text
    assert "/proc/meminfo" in diagnostic_text
    assert "/sys/kernel/mm/hugepages" in pools_text

    overrides = content.presentation_catalog["presentation_catalog"]["source_overrides"]
    assert set(overrides["os.postgresql_huge_pages"]) == {
        "server_version_num",
        "huge_pages_requested",
        "huge_pages_actual",
        "huge_pages_status_source",
        "postgresql_huge_page_size_bytes",
        "shared_buffers_bytes",
        "shared_memory_size_bytes",
        "required_huge_pages",
        "required_huge_pages_bytes",
        "os_default_huge_page_size_bytes",
        "default_pool_matches_postgresql_page_size",
        "default_pool_total_pages",
        "default_pool_used_pages",
        "default_pool_free_pages",
        "default_pool_reserved_pages",
        "default_pool_free_unreserved_pages",
        "default_pool_surplus_pages",
        "default_pool_total_bytes",
        "default_pool_shortfall_pages",
        "host_ram_bytes",
        "host_page_tables_bytes",
        "host_page_tables_pct_ram",
        "host_secondary_page_tables_bytes",
        "host_hugetlb_bytes",
        "postgres_instance_procfs_status",
        "postgres_process_count",
        "postgres_vmpte_bytes",
        "postgres_vmpte_share_pct",
        "postgres_main_hugetlb_bytes",
        "transparent_huge_pages_mode",
        "anonymous_huge_pages_bytes",
        "risk_level",
        "recommendation",
    }
    assert set(overrides["os.huge_page_pools"]) == {
        "page_size_bytes",
        "is_default_size",
        "total_pages",
        "used_pages",
        "free_pages",
        "reserved_pages",
        "free_unreserved_pages",
        "surplus_pages",
        "pool_total_bytes",
        "pool_used_bytes",
        "pool_reserved_bytes",
        "pool_free_unreserved_bytes",
        "numa_distribution",
        "numa_nodes_with_pages",
    }


def test_local_only_python_items_do_not_bypass_host_access(content_path: Path) -> None:
    content = load_content(content_path)
    filesystem_calls = {
        "exists",
        "glob",
        "is_dir",
        "is_file",
        "iterdir",
        "lstat",
        "read_bytes",
        "read_text",
        "readlink",
        "resolve",
        "stat",
    }
    forbidden_modules = {"grp", "pwd", "shutil", "subprocess"}
    collector_local_helpers = {
        "_candidate_client_secret_files",
        "_cron_files",
        "_encrypted_block_sources",
        "_inspect_client_secret_file",
        "_inspect_cron_file",
        "_inspect_history_file",
        "_mount_table",
        "_permission_findings",
        "_postgres_systemd_files",
        "_postgres_systemd_unit_names",
        "_run_command",
        "_sudoers_files",
        "_symlink_findings",
        "_tls_private_key_findings",
        "_world_writable_tree_findings",
    }

    for source_id, manifest in content.pythons.items():
        if not manifest.get("local_only"):
            continue
        source_path = content.path / "python" / manifest["python_file"]
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                owner = ast.unparse(node.func.value)
                if node.func.attr in filesystem_calls and not owner.startswith("ctx.host"):
                    raise AssertionError(
                        f"{source_id} bypasses ctx.host with {owner}.{node.func.attr}"
                    )
            if isinstance(node, ast.Name) and node.id in forbidden_modules:
                raise AssertionError(f"{source_id} uses collector-local module {node.id}")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in collector_local_helpers
            ):
                raise AssertionError(
                    f"{source_id} uses collector-local helper {node.func.id}"
                )


def test_validator_requires_async_local_only_python_function(
    content_path: Path,
    tmp_path: Path,
) -> None:
    content = load_content(content_path)
    python_root = tmp_path / "python"
    python_root.mkdir()
    (python_root / "sync_source.py").write_text(
        "def collect(ctx):\n    return None\n",
        encoding="utf-8",
    )
    invalid = replace(
        content,
        path=tmp_path,
        pythons={
            "test.sync": {
                "title": "Synchronous host source",
                "python_file": "sync_source.py",
                "function": "collect",
                "local_only": True,
                "timeout_ms": 1000,
            }
        },
    )

    issues = validate_content(invalid)

    assert any(
        issue.code == "python_function" and "must be async" in issue.message
        for issue in issues
    )


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
        and (
            metric.get("top_n")
            or ((metric.get("table") or {}).get("limit"))
        )
    }
    assert len(bounded_metrics) == 37

    for metric_id, metric in bounded_metrics.items():
        query = content.queries[metric["source_query"]]
        for variant in query.get("variants") or []:
            sql = (content.path / "queries" / variant["sql_file"]).read_text(encoding="utf-8")
            assert re.search(r"\border\s+by\b", sql, re.IGNORECASE), metric_id
            assert re.search(r"\blimit\s+\d+\b", sql, re.IGNORECASE), metric_id


def test_pg_stat_kcache_metrics_use_independent_reset_safe_sources(content_path: Path) -> None:
    content = load_content(content_path)
    table_metrics = {
        "statements.kernel_cpu_delta",
        "statements.filesystem_io_delta",
        "statements.cpu_efficiency_delta",
        "statements.context_switches_delta",
        "statements.page_faults_delta",
        "statements.io_attribution_delta",
        "statements.planning_kernel_delta",
    }
    chart_metrics = {
        "database.kernel_cpu_rate",
        "database.filesystem_io_rate",
        "database.page_fault_rate",
    }
    source_ids = {
        content.metrics[metric_id]["source_query"]
        for metric_id in table_metrics | chart_metrics
    }
    sql_files = {
        content.queries[source_id]["variants"][0]["sql_file"]
        for source_id in source_ids
    }

    assert len(source_ids) == 10
    assert len(sql_files) == 10
    for metric_id in table_metrics:
        metric = content.metrics[metric_id]
        assert metric["table"]["epoch_refs"] == ["dimensions.kcache_stats_since"]
        source = content.queries[metric["source_query"]]
        assert source["optional"] is True
        sql = (content.path / "queries" / source["variants"][0]["sql_file"]).read_text(
            encoding="utf-8"
        ).lower()
        assert "from pg_stat_kcache()" in sql
        assert "k.top is true" in sql
        assert "k.stats_since as kcache_stats_since" in sql
        assert "s.query as query" in sql
        assert "limit 250" in sql

    for metric_id in chart_metrics:
        metric = content.metrics[metric_id]
        assert metric["epoch_refs"] == ["dimensions.kcache_stats_since"]
        source = content.queries[metric["source_query"]]
        assert source["optional"] is True
        sql = (content.path / "queries" / source["variants"][0]["sql_file"]).read_text(
            encoding="utf-8"
        ).lower()
        assert "from pg_stat_kcache()" in sql
        assert "k.top is true" in sql
        assert "min(k.stats_since) as kcache_stats_since" in sql


def test_pg_stat_kcache_chart_units_and_kinds_are_explicit(content_path: Path) -> None:
    content = load_content(content_path)

    cpu = content.metrics["database.kernel_cpu_rate"]
    filesystem = content.metrics["database.filesystem_io_rate"]
    faults = content.metrics["database.page_fault_rate"]

    assert cpu["chart"] == {
        "kind": "stacked_area",
        "series_order": "configured",
        "unit": "cpu_seconds/s",
    }
    assert filesystem["chart"]["kind"] == "line"
    assert filesystem["chart"]["unit"] == "bytes/s"
    assert faults["chart"]["kind"] == "stacked_area"
    assert faults["chart"]["unit"] == "count/s"
    assert content.presentation_catalog["presentation_catalog"]["units"]["cpu_seconds/s"]["symbol"] == "CPU-s/s"


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
    plan_low = build_plan(content, 90000)
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
        mode=ONE_SHOT_MODE,
        collection_mode=REMOTE_DB_ONLY_COLLECTION_MODE,
    )

    by_id = {item.item_id: item for item in plan.items}
    assert by_id["os.kernel_version"].status == "skipped"
    assert by_id["os.kernel_version"].reason == "no data because remote call"
    assert by_id["os.postgresql_huge_pages"].status == "skipped"
    assert by_id["os.huge_page_pools"].status == "skipped"
    assert by_id["backend_os.postgres_main_process_linked_libraries"].status == "skipped"
    assert by_id["backend_os.postgres_main_process_linked_libraries"].reason == (
        "no data because remote call"
    )
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
    assert by_id["overview.database_volume"].source_metadata["display"]["default_sort"] == {
        "column": "database_size_bytes",
        "direction": "desc",
    }
    assert by_id["overview.pg_settings"].source_metadata["evaluation"] == {
        "summary_title": "PostgreSQL settings require review",
        "recommendation": (
            "Review pending-restart settings and validate work_mem against concurrency "
            "and query spill evidence before changing it globally."
        ),
    }
    assert by_id["storage_vacuum.autovacuum_queue"].source_metadata["display"]["default_sort"] == {
        "column": "priority_factor",
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
    jobs_by_source = {job.source_id: job for job in plan.source_jobs}
    by_id = {item.item_id: item for item in plan.items}
    assert by_source["database.database_stats"].collection_scope == "once"
    assert by_source["io.pg_stat_io"].collection_scope == "once"
    assert jobs_by_source["metrics.database_transaction_rate"].collection_scope == "every_snapshot"
    assert jobs_by_source["metrics.wal_growth_rate"].collection_scope == "every_snapshot"
    assert jobs_by_source["metrics.io_read_write_rate"].collection_scope == "every_snapshot"
    assert jobs_by_source["metrics.database_workload_delta"].collection_scope == "window_endpoints"
    assert jobs_by_source["metrics.statements_total_time_delta"].collection_scope == "window_endpoints"
    assert by_source["objects.table_workload"].collection_scope == "once"
    assert by_source["objects.table_io"].collection_scope == "once"
    assert by_source["objects.index_workload"].collection_scope == "once"
    assert jobs_by_source["metrics.database_transaction_rate"].job_id == (
        "metrics.database_transaction_rate"
    )
    database_usage = by_id["overview.database_stats"].source_metadata["query_usage"]
    assert database_usage["query_id"] == "database.database_stats"
    assert database_usage["isolation"] == "isolated"
    assert database_usage["item_count"] == 1
    assert database_usage["item_ids"] == ["overview.database_stats"]
    assert database_usage["other_item_ids"] == []
    assert by_id["snapshot_charts_db.database_transaction_rate"].source_metadata["source_query"] == (
        "metrics.database_transaction_rate"
    )
    assert by_id["snapshot_charts_db.database_transaction_rate"].source_metadata[
        "database_scope"
    ] == "all_databases"
    assert by_id["snapshot_delta_workload.sql_time_delta"].source_metadata[
        "database_scope"
    ] == "current_database"
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
        usage = item.source_metadata.get("query_usage")
        if not usage:
            continue
        assert usage["isolation"] == "isolated", item.item_id
        assert usage["item_count"] == 1, item.item_id
        assert usage["item_ids"] == [item.item_id], item.item_id
        assert usage["other_item_ids"] == [], item.item_id

    assert {job.source_id for job in plan.source_jobs} == set(source_queries)
    for job in plan.source_jobs:
        usage = job.source_metadata["query_usage"]
        assert usage["isolation"] == "isolated", job.job_id
        assert usage["item_count"] == 1, job.job_id
        assert len(usage["item_ids"]) == 1, job.job_id
        assert usage["other_item_ids"] == [], job.job_id


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
    assert by_id["backend_os.postgres_main_process_linked_libraries"].source_kind == "python"
    assert by_id["backend_os.postgres_main_process_linked_libraries"].python_file == (
        "backend/postgres_main_process_linked_libraries.py"
    )
    assert content.pythons["backend.postgres_main_process_linked_libraries"]["local_only"] is True
    assert by_id["backend_os.postgres_main_process_linked_libraries"].collection_scope == "once"
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
        if item.source_kind == "query"
    ]
    assert visible_queries
    assert {item.collection_scope for item in visible_queries} == {"once"}

    repeated_queries = [
        item
        for item in plan.source_jobs
        if item.source_kind == "query" and item.collection_scope == "every_snapshot"
    ]
    assert repeated_queries
    for item in repeated_queries:
        metric = metrics_by_source[item.source_id]
        assert metric.get("result") != "table"
        assert not metric.get("table")

    endpoint_queries = [
        item
        for item in plan.source_jobs
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


def test_remaining_chart_sections_have_complete_and_consistent_contracts(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    chart_items = [
        item_id
        for section_id, _item_key, item_id, _item in iter_report_items(content)
        if section_id in {"snapshot_charts_os", "snapshot_charts_db"}
    ]
    assert len(chart_items) == 43
    for item_id in chart_items:
        assert "## Automatic evaluation" in content.instructions[item_id]["text"], item_id

    assert content.metrics["os.memory_pressure"]["chart"]["kind"] == "line"
    assert content.metrics["database.tuple_access_rate"]["chart"]["kind"] == "line"
    assert "delta_adjustment" not in content.metrics["database.transaction_rate"]["series"][0]
    assert content.metrics["wal.growth_rate"]["partition_by"] == ["dimensions.scope"]

    for metric_id, metric in content.metrics.items():
        if metric_id.startswith("objects.tables_top_"):
            assert metric["top_n"]["key_refs"] == [
                "dimensions.database",
                "dimensions.relation_id",
            ]
        if metric_id.startswith("objects.indexes_top_"):
            assert metric["top_n"]["key_refs"] == [
                "dimensions.database",
                "dimensions.index_id",
            ]

    for source_id in ("metrics.io_read_write_rate", "metrics.wal_growth_rate"):
        for variant in content.queries[source_id]["variants"]:
            sql = (content.path / "queries" / variant["sql_file"]).read_text(
                encoding="utf-8"
            ).lower()
            assert "'cluster'::text as scope" in sql
            assert "group by rollup" not in sql
            assert "backend_type, 'total'" not in sql


def test_object_and_index_queries_bound_expensive_size_calls(content_path: Path) -> None:
    content = load_content(content_path)
    for source_id in (
        "objects.table_workload",
        "indexes.invalid_indexes",
        "indexes.unused_indexes",
        "indexes.duplicate_indexes",
        "indexes.tables_without_pk_or_unique",
        "indexes.large_indexes",
    ):
        variant = content.queries[source_id]["variants"][-1]
        sql = (content.path / "queries" / variant["sql_file"]).read_text(
            encoding="utf-8"
        ).lower()
        assert "limit" in sql, source_id
        if "pg_relation_size" in sql or "pg_total_relation_size" in sql:
            assert sql.find("limit") < max(
                sql.find("pg_relation_size"),
                sql.find("pg_total_relation_size"),
            ), source_id
