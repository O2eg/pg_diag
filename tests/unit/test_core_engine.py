from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import time

import pytest
import yaml

from pg_diag import runtime_config
from pg_diag.artifact import (
    apply_database_scope_presentation,
    artifact_has_errors,
    item_from_plan,
    report_output_paths,
    write_json,
    write_text_secure,
)
from pg_diag.cli import build_parser
from pg_diag.content_loader import ContentLoadError, load_content
from pg_diag.errors import ValidationError
from pg_diag.executors.python import execute_python_item
from pg_diag.metric_engine import build_metric_item
from pg_diag.planner import PlannedItem, build_plan
from pg_diag.render.html import _publicize_artifact_for_render, render_html
from pg_diag.snapshots import _collect_db_samples, _execute_query_batch
from pg_diag.validator import validate_content


def _planned_query() -> PlannedItem:
    return PlannedItem(
        item_id="s.q",
        section_id="s",
        item_key="q",
        title="Query",
        source_kind="query",
        source_id="q",
        status="planned",
        collection_scope="every_snapshot",
    )


class _BatchTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _BatchConnection:
    def __init__(self) -> None:
        self.readonly_transactions = 0
        self.executed: list[tuple[str, str]] = []

    def transaction(self, *, readonly: bool):
        assert readonly is True
        self.readonly_transactions += 1
        return _BatchTransaction()

    async def execute(self, sql: str, value: str) -> None:
        self.executed.append((sql, value))


def _test_column(name: str, *, value_kind: str = "integer") -> dict:
    if value_kind == "integer":
        return {
            "name": name,
            "label": name,
            "value_kind": "integer",
            "semantic_role": "gauge",
            "quantity": "count",
            "unit": "count",
            "quality": "exact",
            "nullable": True,
            "encoding": "json_number",
        }
    return {
        "name": name,
        "label": name,
        "value_kind": "text",
        "semantic_role": "label",
        "quantity": "text",
        "unit": "none",
        "quality": "exact",
        "nullable": True,
        "encoding": "json_string",
    }


def _artifact(*, title: str = "Test", data: str = "ok") -> dict:
    return {
        "artifact_schema_version": runtime_config.ARTIFACT_SCHEMA_VERSION,
        "generator": {"name": "pg_diag", "version": "test"},
        "content": {
            "schema_version": runtime_config.SUPPORTED_CONTENT_SCHEMA_VERSION,
            "content_path": "/tmp/test-content",
            "checksum": "sha256:test",
            "report_id": "test",
            "document": {
                "report": {"id": "test", "title": "Test"},
                "runtime_policy": {},
                "defaults": {"table": {"page_size": 25}},
                "sections": {},
                "catalogs": {
                    "presentation": {
                        "units": {"none": {}, "count": {}},
                    }
                },
                "queries": {},
                "scripts": {},
                "metrics": {},
                "python_sources": {},
                "sampler_providers": {},
                "instructions": {},
                "field_reference": {"report": "Report metadata."},
            },
            "provenance": {"report": ["report.yaml"]},
        },
        "report": {"id": "test", "title": title},
        "runtime": {"mode": "snapshot", "collection_mode": "remote-db-only"},
        "display": {
            "table": {"page_size": 25},
            "database_scope_presentation": {
                "metadata_field": "database_scope",
                "values": {
                    "all_databases": {"title_suffix": " (All databases)", "hidden_columns": []},
                    "current_database": {
                        "title_suffix": " (Only {current_database})",
                        "hidden_columns": ["datname", "database_name"],
                    },
                },
            },
        },
        "sections": [
            {"section_id": "s", "title": "S", "state": "expanded", "items": ["s.i"]}
        ],
        "items": {
            "s.i": {
                "item_id": "s.i",
                "section_id": "s",
                "item_key": "i",
                "title": "Item",
                "source_kind": "query",
                "collection_scope": "once",
                "collection_status": "ok",
                "severity_level": "unknown",
                "state": "expanded",
                "result": {"kind": "plain_text", "data": data},
                "source_metadata": {},
                "diagnostics": [],
                "issues": {},
            }
        },
        "query_texts": {},
        "snapshot_schemas": {},
        "snapshots": [],
        "diagnostics": [],
    }


def test_database_scope_presentation_labels_items_and_hides_redundant_datname() -> None:
    artifact = _artifact()
    artifact["runtime"]["current_database"] = "pg_diag_loadtest"
    artifact["items"]["s.i"].update(
        {
            "title": "SQL Time Delta",
            "source_metadata": {
                "database_scope": "current_database",
                "display": {"default_sort": {"column": "datname", "direction": "asc"}},
            },
            "result": {
                "kind": "table",
                "columns": [
                    {"name": "datname"},
                    {"name": "database_name"},
                    {"name": "calls_delta"},
                ],
                "rows": [["pg_diag_loadtest", "pg_diag_loadtest", 42]],
                "row_count": 1,
            },
        }
    )
    artifact["items"]["s.all"] = {
        "title": "Database Workload Delta",
        "source_metadata": {"database_scope": "all_databases"},
        "result": {
            "kind": "table",
            "columns": [{"name": "datname"}, {"name": "commit_delta"}],
            "rows": [["postgres", 1], ["pg_diag_loadtest", 2]],
            "row_count": 2,
        },
    }

    apply_database_scope_presentation(artifact)
    apply_database_scope_presentation(artifact)

    current = artifact["items"]["s.i"]
    assert current["title"] == "SQL Time Delta (Only pg_diag_loadtest)"
    assert [column["name"] for column in current["result"]["columns"]] == ["calls_delta"]
    assert current["result"]["rows"] == [[42]]
    assert current["source_metadata"]["display"] == {}

    all_databases = artifact["items"]["s.all"]
    assert all_databases["title"] == "Database Workload Delta (All databases)"
    assert [column["name"] for column in all_databases["result"]["columns"]] == [
        "datname",
        "commit_delta",
    ]


def test_snapshot_schedule_is_bounded_and_includes_window_end() -> None:
    assert runtime_config.snapshots_schedule_offsets(600, 30) == [
        float(offset) for offset in range(0, 601, 30)
    ]
    assert runtime_config.snapshots_schedule_offsets(35, 20) == [0.0, 20.0, 35.0]


def test_snapshot_schedule_rejects_non_positive_values() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        runtime_config.snapshots_schedule_offsets(0, 5)
    with pytest.raises(ValueError, match="must be positive"):
        runtime_config.snapshots_schedule_offsets(30, 0)
    assert runtime_config.validate_snapshots_window(30, 600) == (
        "snapshots requires --interval-seconds not greater than --duration-seconds"
    )


def test_postgresql_settings_is_collected_once_in_snapshots_mode(content_path: Path) -> None:
    content = load_content(content_path)
    plan = build_plan(content, 180000, mode=runtime_config.SNAPSHOTS_MODE)
    item = {entry.item_id: entry for entry in plan.items}["overview.pg_settings"]

    assert item.collection_scope == runtime_config.ONCE_COLLECTION_SCOPE


def test_cli_finds_source_tree_content_outside_repository(
    content_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    args = build_parser().parse_args(["validate"])

    assert Path(args.content).resolve() == content_path.resolve()


def test_db_snapshots_store_only_varying_table_data(monkeypatch: pytest.MonkeyPatch) -> None:
    planned = _planned_query()
    query_texts: dict[str, str] = {}
    snapshot_schemas: dict[str, dict] = {}

    async def execute_stub(content, conn, item):
        return item_from_plan(
            item,
            collection_status="ok",
            timing_ms=12.5,
            result={
                "kind": "table",
                "columns": [
                    {"name": "query_id"},
                    {"name": "query"},
                    {"name": "value"},
                ],
                "rows": [["42", "select 42", 42]],
                "row_count": 1,
            },
            diagnostics=[{"level": "warning", "code": "test", "message": "test"}],
        )

    monkeypatch.setattr(runtime_config, "snapshots_schedule_offsets", lambda *_args: [0.0])
    monkeypatch.setattr("pg_diag.snapshots.execute_query_item", execute_stub)

    conn = _BatchConnection()
    snapshots, diagnostics, latest = asyncio.run(
        _collect_db_samples(
            SimpleNamespace(
                report={
                    "runtime_policy": {
                        "query_text_catalog": {
                            "id_column_suffix": "query_id",
                            "value_column_remove_suffix": "_id",
                        }
                    }
                }
            ),
            conn,
            [planned],
            30,
            15,
            query_texts=query_texts,
            snapshot_schemas=snapshot_schemas,
        )
    )

    compact = snapshots[0]["items"]["s.q"]
    assert compact == {
        "collection_status": "ok",
        "result": {"kind": "table", "rows": [["42", 42]]},
    }
    assert [column["name"] for column in latest["s.q"]["result"]["columns"]] == [
        "query_id",
        "value",
    ]
    assert query_texts == {"42": "select 42"}
    assert [column["name"] for column in snapshot_schemas["s.q"]["columns"]] == [
        "query_id",
        "value",
    ]
    assert diagnostics == []
    assert conn.readonly_transactions == 1


def test_db_sampler_does_not_start_stale_final_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    async def execute_stub(content, conn, item):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.16)
        return item_from_plan(
            item,
            collection_status="empty",
            result={"kind": "table", "columns": [], "rows": [], "row_count": 0},
        )

    monkeypatch.setattr(runtime_config, "snapshots_schedule_offsets", lambda *_args: [0.0, 0.05])
    monkeypatch.setattr("pg_diag.snapshots.execute_query_item", execute_stub)

    conn = _BatchConnection()
    snapshots, diagnostics, _latest = asyncio.run(
        _collect_db_samples(SimpleNamespace(report={}), conn, [_planned_query()], 0.05, 0.05)
    )

    assert calls == 1
    assert len(snapshots) == 1
    assert diagnostics[0]["code"] == "db_sampler_lag"
    assert conn.readonly_transactions == 1


def test_window_endpoint_queries_share_one_read_only_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def execute_stub(content, conn, item):
        calls.append(item.item_id)
        return item_from_plan(
            item,
            collection_status="ok",
            result={"kind": "table", "columns": [], "rows": [], "row_count": 0},
        )

    monkeypatch.setattr("pg_diag.snapshots.execute_query_item", execute_stub)
    conn = _BatchConnection()
    queries = [_planned_query(), replace(_planned_query(), item_id="s.q2", item_key="q2")]

    snapshot, items, error_counts = asyncio.run(
        _execute_query_batch(SimpleNamespace(report={}), conn, queries)
    )

    assert calls == ["s.q", "s.q2"]
    assert set(snapshot["items"]) == {"s.q", "s.q2"}
    assert set(items) == {"s.q", "s.q2"}
    assert not error_counts
    assert conn.readonly_transactions == 1
    assert len(conn.executed) == 0


def test_python_source_timeout_does_not_block_event_loop(tmp_path: Path) -> None:
    python_dir = tmp_path / "python"
    python_dir.mkdir()
    completion_marker = tmp_path / "completed"
    (python_dir / "slow.py").write_text(
        "import time\n"
        "def collect(context):\n"
        "    time.sleep(0.5)\n"
        f"    open({str(completion_marker)!r}, 'w', encoding='utf-8').write('done')\n"
        "    return {'collection_status': 'ok', 'result': {'kind': 'none'}}\n",
        encoding="utf-8",
    )
    content = SimpleNamespace(
        path=tmp_path,
        pythons={
            "test.slow": {
                "python_file": "slow.py",
                "function": "collect",
                "timeout_ms": 50,
            }
        },
        python_catalog={"python_catalog": {"defaults": {}}},
    )
    planned = PlannedItem(
        item_id="s.slow",
        section_id="s",
        item_key="slow",
        title="Slow",
        source_kind="python",
        source_id="test.slow",
        status="planned",
        python_file="slow.py",
    )

    started = time.monotonic()
    item = asyncio.run(execute_python_item(content, SimpleNamespace(), planned))
    elapsed = time.monotonic() - started

    assert elapsed < 0.3
    assert item["collection_status"] == "error"
    assert item["reason"] == "Python source timed out after 50 ms"
    assert item["diagnostics"][0]["code"] == "python_timeout"
    time.sleep(0.55)
    assert not completion_marker.exists()


def test_python_source_helpers_are_isolated_per_content_pack(tmp_path: Path) -> None:
    planned = PlannedItem(
        item_id="s.helper",
        section_id="s",
        item_key="helper",
        title="Helper",
        source_kind="python",
        source_id="test.helper",
        status="planned",
        python_file="source.py",
    )

    def content_pack(root: Path, value: str) -> SimpleNamespace:
        python_dir = root / "python"
        python_dir.mkdir(parents=True)
        (python_dir / "_helper.py").write_text(f"VALUE = {value!r}\n", encoding="utf-8")
        (python_dir / "source.py").write_text(
            "from _helper import VALUE\n"
            "async def collect(context):\n"
            "    return {\n"
            "        'collection_status': 'ok',\n"
            "        'result': {'kind': 'plain_text', 'data': VALUE},\n"
            "    }\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            path=root,
            pythons={
                "test.helper": {
                    "python_file": "source.py",
                    "function": "collect",
                    "timeout_ms": 1000,
                }
            },
            python_catalog={"python_catalog": {"defaults": {}}},
        )

    first = asyncio.run(
        execute_python_item(content_pack(tmp_path / "first", "first"), SimpleNamespace(), planned)
    )
    second = asyncio.run(
        execute_python_item(content_pack(tmp_path / "second", "second"), SimpleNamespace(), planned)
    )

    assert first["result"]["data"] == "first"
    assert second["result"]["data"] == "second"


def test_artifact_writer_rejects_nan_and_uses_private_permissions(tmp_path: Path) -> None:
    invalid = _artifact()
    invalid["runtime"]["bad"] = float("nan")
    invalid_path = tmp_path / "invalid.json"

    with pytest.raises(ValidationError, match="strict JSON"):
        write_json(invalid_path, invalid)
    assert not invalid_path.exists()

    output = tmp_path / "nested" / "report.json"
    write_json(output, _artifact())
    assert output.stat().st_mode & 0o777 == 0o600
    assert json.loads(output.read_text(encoding="utf-8"))["report"]["id"] == "test"


def test_artifact_validator_reports_unhashable_contract_values(tmp_path: Path) -> None:
    artifact = _artifact()
    artifact["items"]["s.i"]["collection_status"] = []

    with pytest.raises(ValidationError, match="collection_status"):
        write_json(tmp_path / "invalid.json", artifact)


def test_artifact_validator_accepts_consistent_interval_coverage(tmp_path: Path) -> None:
    artifact = _artifact()
    artifact["items"]["s.i"]["result"] = {
        "kind": "table",
            "columns": [_test_column("value")],
        "rows": [[1]],
        "row_count": 1,
        "interval_coverage": {
            "total": 3,
            "comparable": 1,
            "unmatched": 2,
            "invalid": 0,
            "counts": {"ok": 1, "missing_start": 1, "missing_end": 1},
        },
    }

    write_json(tmp_path / "valid.json", artifact)


def test_artifact_validator_accepts_epoch_changed_as_invalid_interval(tmp_path: Path) -> None:
    artifact = _artifact()
    artifact["items"]["s.i"]["result"] = {
        "kind": "chart",
        "series": [],
        "interval_coverage": {
            "total": 1,
            "comparable": 0,
            "unmatched": 0,
            "invalid": 1,
            "counts": {"epoch_changed": 1},
        },
    }

    write_json(tmp_path / "valid-epoch-change.json", artifact)


def test_artifact_validator_rejects_inconsistent_interval_coverage(tmp_path: Path) -> None:
    artifact = _artifact()
    artifact["items"]["s.i"]["result"] = {
        "kind": "chart",
        "series": [],
        "interval_coverage": {
            "total": 2,
            "comparable": 2,
            "unmatched": 0,
            "invalid": 0,
            "counts": {"ok": 1},
        },
    }

    with pytest.raises(ValidationError, match="counts do not match total"):
        write_json(tmp_path / "invalid.json", artifact)


def test_artifact_validator_rejects_non_json_container_types(tmp_path: Path) -> None:
    artifact = _artifact()
    artifact["runtime"]["tuple_value"] = (1, 2)

    with pytest.raises(ValidationError, match="unsupported tuple"):
        write_json(tmp_path / "invalid.json", artifact)


def test_artifact_validator_rejects_invalid_item_collected_at(tmp_path: Path) -> None:
    artifact = _artifact()
    artifact["items"]["s.i"]["collected_at"] = ""

    with pytest.raises(ValidationError, match="collected_at must be a non-empty string"):
        write_json(tmp_path / "invalid.json", artifact)


def test_artifact_validator_rejects_invalid_delta_window(tmp_path: Path) -> None:
    artifact = _artifact()
    artifact["items"]["s.i"]["result"] = {
        "kind": "table",
        "columns": [_test_column("value")],
        "rows": [[1]],
        "row_count": 1,
        "delta_window": {
            "start_time": "2026-07-05T00:00:00+00:00",
            "finish_time": "2026-07-05T00:00:05+00:00",
            "duration_seconds": -1,
        },
    }

    with pytest.raises(ValidationError, match="duration_seconds must be non-negative"):
        write_json(tmp_path / "invalid.json", artifact)


def test_artifact_validator_rejects_invalid_content_provenance(tmp_path: Path) -> None:
    artifact = _artifact()
    artifact["content"]["provenance"] = {"queries/q": "queries.yaml"}

    with pytest.raises(ValidationError, match="content.provenance"):
        write_json(tmp_path / "invalid.json", artifact)


def test_artifact_validator_rejects_prior_schema_versions(tmp_path: Path) -> None:
    artifact = _artifact()
    artifact["artifact_schema_version"] = runtime_config.ARTIFACT_SCHEMA_VERSION - 1

    with pytest.raises(ValidationError, match="Unsupported artifact schema version"):
        write_json(tmp_path / "old.json", artifact)


def test_artifact_validator_requires_unified_content_document(tmp_path: Path) -> None:
    artifact = _artifact()
    del artifact["content"]["document"]

    with pytest.raises(ValidationError, match="content.document"):
        write_json(tmp_path / "invalid.json", artifact)


def test_artifact_validator_rejects_internal_result_columns(tmp_path: Path) -> None:
    artifact = _artifact()
    artifact["items"]["s.i"]["result"] = {
        "kind": "table",
        "columns": [_test_column("epoch_ns"), _test_column("tag_value", value_kind="text")],
        "rows": [[1783182080458119000, "visible"]],
        "row_count": 1,
    }

    with pytest.raises(ValidationError, match="exposes internal columns"):
        write_json(tmp_path / "invalid.json", artifact)


def test_artifact_v3_accepts_compact_snapshot_rows_with_shared_schema(tmp_path: Path) -> None:
    artifact = _artifact()
    artifact["items"]["s.i"]["result"] = {
        "kind": "table",
        "columns": [_test_column("value")],
        "rows": [[2]],
        "row_count": 1,
    }
    artifact["snapshot_schemas"] = {"s.i": {"columns": [_test_column("value")]}}
    artifact["snapshots"] = [
        {
            "timestamp": "2026-07-09T00:00:00+00:00",
            "items": {
                "s.i": {
                    "collection_status": "ok",
                    "result": {"kind": "table", "rows": [[1]]},
                }
            },
        }
    ]

    output = tmp_path / "report.json"
    write_json(output, artifact)

    assert json.loads(output.read_text(encoding="utf-8"))["snapshot_schemas"]["s.i"] == {
        "columns": [_test_column("value")]
    }
    public = _publicize_artifact_for_render(artifact)
    assert public["runtime"]["snapshot_count"] == 1
    assert public["snapshots"] == []
    assert public["snapshot_schemas"] == {}


def test_renderer_projection_does_not_copy_raw_snapshots() -> None:
    class RawSnapshot:
        def __deepcopy__(self, memo):
            raise AssertionError("raw snapshots must not be deep-copied for HTML")

    artifact = _artifact()
    artifact["snapshots"] = [RawSnapshot()]

    public = _publicize_artifact_for_render(artifact)

    assert public["runtime"]["snapshot_count"] == 1
    assert public["snapshots"] == []


def test_secure_text_writer_replaces_existing_file_atomically(tmp_path: Path) -> None:
    output = tmp_path / "report.html"
    output.write_text("old", encoding="utf-8")
    output.chmod(0o666)

    write_text_secure(output, "new")

    assert output.read_text(encoding="utf-8") == "new"
    assert output.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".report.html.*.tmp"))


def test_output_paths_must_be_distinct() -> None:
    with pytest.raises(ValueError, match="must be different"):
        report_output_paths("out", json_out="same", html_out="same")


def test_artifact_error_status_includes_historical_snapshot_failures() -> None:
    artifact = _artifact()
    artifact["snapshots"] = [
        {
            "timestamp": "2026-07-09T00:00:00+00:00",
            "items": {
                "s.q": {
                    "collection_status": "error",
                    "result": {"kind": "none"},
                }
            },
        }
    ]

    assert artifact_has_errors(artifact)


def test_renderer_does_not_rescan_replacement_payloads() -> None:
    html = render_html(_artifact(title="__PAYLOAD__", data="__APEXCHARTS_JS__"))

    assert "<title>__PAYLOAD__</title>" in html
    assert '"data":"__APEXCHARTS_JS__"' in html


def test_renderer_excludes_hidden_sections_and_items() -> None:
    artifact = _artifact()
    artifact["sections"][0]["state"] = "hidden"

    public = _publicize_artifact_for_render(artifact)

    assert public["sections"] == []
    assert public["items"] == {}


def test_metric_propagates_source_error_instead_of_reporting_empty() -> None:
    planned = PlannedItem(
        item_id="s.metric",
        section_id="s",
        item_key="metric",
        title="Metric",
        source_kind="metric",
        source_id="m",
        status="planned",
    )
    metric = {
        "source_query": "q",
        "series": [{"name": "value", "value_ref": "value"}],
    }
    snapshots = [
        {
            "timestamp": "2026-07-09T00:00:00+00:00",
            "items": {
                "s.q": {
                    "collection_status": "error",
                    "reason": "query failed",
                    "result": {"kind": "none"},
                }
            },
        }
    ]

    item = build_metric_item(
        planned,
        metric,
        snapshots,
        {},
        {"q": "s.q"},
        {"s.q": {"_result_columns": [{"name": "value"}]}},
    )

    assert item["collection_status"] == "error"
    assert item["reason"] == "query failed"
    assert item["diagnostics"][0]["code"] == "metric_source_samples"


def test_metric_propagates_planned_source_status_without_sample_rows() -> None:
    planned = PlannedItem(
        item_id="s.metric",
        section_id="s",
        item_key="metric",
        title="Metric",
        source_kind="metric",
        source_id="m",
        status="planned",
    )

    item = build_metric_item(
        planned,
        {"source_query": "q", "series": [{"name": "value", "value_ref": "value"}]},
        [],
        {},
        {"q": "s.q"},
        {
            "s.q": {
                "_collection_status": "unsupported",
                "_reason": "no variant for this server",
            }
        },
    )

    assert item["collection_status"] == "unsupported"
    assert item["reason"] == "no variant for this server"
    assert item["diagnostics"][0]["code"] == "metric_source_status"


def test_validator_reports_invalid_types_without_crashing(content_path: Path) -> None:
    content = load_content(content_path)
    report = deepcopy(content.report)
    report["defaults"]["table"]["page_size"] = "many"
    report["report"]["default_state"] = []
    report["sections"]["overview"]["items"]["server_version"]["state"] = {}
    queries = deepcopy(content.queries)
    queries["cluster.settings"]["variants"][0]["min_pg_version"] = "bad"
    queries["cluster.server_version"]["collection"]["supports"] = [{}]
    metrics = deepcopy(content.metrics)
    metrics["os.cpu_utilization"]["source_query"] = "cluster.settings"
    invalid = replace(content, report=report, queries=queries, metrics=metrics)

    issues = validate_content(invalid)
    codes = {issue.code for issue in issues}

    assert "defaults" in codes
    assert "version_range" in codes
    assert "metric_source" in codes


def test_content_loader_rejects_catalog_path_escape(tmp_path: Path) -> None:
    root = tmp_path / "content"
    root.mkdir()
    (root / "report.yaml").write_text(
        "report:\n"
        "  catalogs:\n"
        "    queries: ../outside.yaml\n",
        encoding="utf-8",
    )

    with pytest.raises(ContentLoadError, match="must stay under"):
        load_content(root)


def test_content_loader_requires_explicit_catalog_paths(content_path: Path, tmp_path: Path) -> None:
    copied = tmp_path / "content"
    shutil.copytree(content_path, copied)
    report_path = copied / "report.yaml"
    report = yaml.safe_load(report_path.read_text(encoding="utf-8"))
    del report["report"]["catalogs"]["scripts"]
    report_path.write_text(yaml.safe_dump(report, sort_keys=False), encoding="utf-8")

    with pytest.raises(ContentLoadError, match="Script catalog path must be a non-empty relative path"):
        load_content(copied)


def test_checksum_tracks_configured_sql_root(content_path: Path, tmp_path: Path) -> None:
    copied = tmp_path / "content"
    shutil.copytree(content_path, copied)
    query_index_path = copied / "queries.yaml"
    query_index = yaml.safe_load(query_index_path.read_text(encoding="utf-8"))
    query_index["query_catalog"]["sql_root"] = "custom_sql"
    query_index_path.write_text(yaml.safe_dump(query_index, sort_keys=False), encoding="utf-8")
    (copied / "queries").rename(copied / "custom_sql")

    before = load_content(copied).checksum
    sql_file = next((copied / "custom_sql").rglob("*.sql"))
    sql_file.write_text(sql_file.read_text(encoding="utf-8") + "\n-- checksum test\n", encoding="utf-8")
    after = load_content(copied).checksum

    assert before != after
