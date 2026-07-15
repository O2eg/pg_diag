from __future__ import annotations

import asyncio
from io import StringIO
import json
from types import SimpleNamespace

import pytest

import pg_diag.collection as collection_module
from pg_diag import runtime_config
from pg_diag.artifact import item_from_plan
from pg_diag.artifact import report_output_paths
from pg_diag.errors import PgDiagError, UnsupportedServerVersion
from pg_diag.planner import PlannedItem, SourceJob
from pg_diag.progress import ProgressReporter
from pg_diag.sampler_runtime import SamplerCollection
from pg_diag.one_shot import collect_one_shot
from pg_diag.snapshots import collect_snapshots


class FakeConn:
    async def close(self) -> None:
        pass


def fake_content(tmp_path):
    presentation = {
        "presentation_catalog": {
            "numeric_locale": "en-US",
            "descriptor_fields": [
                "label",
                "value_kind",
                "semantic_role",
                "quantity",
                "unit",
                "quality",
                "nullable",
                "encoding",
            ],
            "value_kinds": ["text"],
            "semantic_roles": ["label"],
            "qualities": ["exact"],
            "encodings": ["json_string"],
            "units": {"none": {}},
            "type_defaults": {
                "text": {
                    "value_kind": "text",
                    "semantic_role": "label",
                    "quantity": "text",
                    "unit": "none",
                    "quality": "exact",
                    "nullable": True,
                    "encoding": "json_string",
                }
            },
            "rules": [],
            "source_overrides": {},
            "label_terms": {},
            "unit_aliases": {"none": "none"},
            "quantity_aliases": {},
            "unit_values": {},
        }
    }
    report = {
        "report": {"id": "test", "title": "Test"},
        "runtime_policy": {
            "fail_fast": False,
            "query_text_catalog": {
                "id_column_suffix": "query_id",
                "value_column_remove_suffix": "_id",
            },
        },
        "defaults": {
            "table": {"page_size": 25},
            "item": {"state": "expanded", "database_scope": "all_databases"},
            "section": {"state": "expanded"},
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
        "sections": {},
    }
    return SimpleNamespace(
        path=tmp_path,
        report=report,
        document={
            "report": report["report"],
            "runtime_policy": report["runtime_policy"],
            "defaults": report["defaults"],
            "sections": report["sections"],
            "catalogs": {"presentation": presentation["presentation_catalog"]},
            "queries": {},
            "scripts": {},
            "metrics": {},
            "python_sources": {},
            "sampler_providers": {},
            "instructions": {},
            "field_reference": {"report": "Report metadata."},
        },
        provenance={"report": ["report.yaml"]},
        presentation_catalog=presentation,
        queries={},
        scripts={},
        metrics={},
        pythons={},
        sampler_providers={},
        checksum="sha256:test",
    )


def fake_plan(mode: str, collection_mode: str):
    return SimpleNamespace(
        mode=mode,
        collection_mode=collection_mode,
        server_version_num=180000,
        supported_server_version=True,
        reason=None,
        sections=[],
        items=[],
        source_jobs=[],
    )


def fake_plan_with_items(mode: str, collection_mode: str, items):
    return SimpleNamespace(
        mode=mode,
        collection_mode=collection_mode,
        server_version_num=180000,
        supported_server_version=True,
        reason=None,
        sections=[
            {
                "section_id": "os",
                "title": "OS",
                "state": "expanded",
                "items": [item.item_id for item in items],
            }
        ],
        items=items,
        source_jobs=[],
    )


def test_report_output_paths_default_to_out_dir() -> None:
    json_path, html_path = report_output_paths("reports/run")

    assert str(json_path) == "reports/run/report.json"
    assert str(html_path) == "reports/run/report.html"


def test_report_output_paths_use_exact_files() -> None:
    json_path, html_path = report_output_paths(
        "reports/run",
        json_out="fixed/report-2026.json",
        html_out="fixed/report-2026.html",
    )

    assert str(json_path) == "fixed/report-2026.json"
    assert str(html_path) == "fixed/report-2026.html"


def test_report_output_paths_select_one_format() -> None:
    json_path, disabled_html_path = report_output_paths(
        "reports/json-only",
        output_formats="json",
    )
    disabled_json_path, html_path = report_output_paths(
        "reports/html-only",
        output_formats=("html",),
    )

    assert str(json_path) == "reports/json-only/report.json"
    assert disabled_html_path is None
    assert disabled_json_path is None
    assert str(html_path) == "reports/html-only/report.html"


@pytest.mark.parametrize(
    ("output_formats", "json_out", "html_out", "message"),
    [
        (("html",), "disabled.json", None, "--json-out requires"),
        (("json",), None, "disabled.html", "--html-out requires"),
        ((), None, None, "at least one report output format"),
        (("xml",), None, None, "unsupported report output format"),
    ],
)
def test_report_output_paths_reject_invalid_format_combinations(
    output_formats,
    json_out,
    html_out,
    message,
) -> None:
    with pytest.raises(ValueError, match=message):
        report_output_paths(
            "reports/run",
            json_out=json_out,
            html_out=html_out,
            output_formats=output_formats,
        )


@pytest.mark.parametrize("output_format", ["html", "json"])
def test_collect_one_shot_writes_only_selected_output_format(
    tmp_path,
    monkeypatch,
    output_format,
) -> None:
    async def connect_stub(*args, **kwargs):
        return FakeConn()

    async def detect_runtime_context_stub(conn):
        return {
            "server_version_num": 180000,
            "server_version": "PostgreSQL 18",
            "current_database": "testdb",
            "current_user": "app",
            "in_recovery": False,
            "capabilities": {},
        }

    render_calls = []

    def render_stub(artifact, **kwargs):
        render_calls.append(artifact)
        return "<html>selected</html>"

    monkeypatch.setattr(collection_module, "connect", connect_stub)
    monkeypatch.setattr(collection_module, "detect_runtime_context", detect_runtime_context_stub)
    monkeypatch.setattr(
        collection_module,
        "build_plan",
        lambda *args, **kwargs: fake_plan(kwargs.get("mode"), kwargs.get("collection_mode")),
    )
    monkeypatch.setattr(collection_module, "render_html", render_stub)

    out_dir = tmp_path / output_format
    asyncio.run(
        collect_one_shot(
            content=fake_content(tmp_path),
            out_dir=out_dir,
            dsn=None,
            connection_kwargs={},
            collection_mode=runtime_config.REMOTE_DB_ONLY_COLLECTION_MODE,
            output_formats=output_format,
            content_validated=True,
        )
    )

    assert (out_dir / "report.html").exists() is (output_format == "html")
    assert (out_dir / "report.json").exists() is (output_format == "json")
    assert bool(render_calls) is (output_format == "html")


def test_collect_snapshots_propagates_json_only_output_format(tmp_path, monkeypatch) -> None:
    async def connect_stub(*args, **kwargs):
        return FakeConn()

    async def detect_runtime_context_stub(conn):
        return {
            "server_version_num": 180000,
            "server_version": "PostgreSQL 18",
            "current_database": "testdb",
            "current_user": "app",
            "in_recovery": False,
            "capabilities": {},
        }

    def unexpected_render(*args, **kwargs):
        raise AssertionError("JSON-only snapshots must not render HTML")

    monkeypatch.setattr(collection_module, "connect", connect_stub)
    monkeypatch.setattr(collection_module, "detect_runtime_context", detect_runtime_context_stub)
    monkeypatch.setattr(
        collection_module,
        "build_plan",
        lambda *args, **kwargs: fake_plan(kwargs.get("mode"), kwargs.get("collection_mode")),
    )
    monkeypatch.setattr(collection_module, "render_html", unexpected_render)

    out_dir = tmp_path / "snapshots-json"
    asyncio.run(
        collect_snapshots(
            content=fake_content(tmp_path),
            out_dir=out_dir,
            dsn=None,
            connection_kwargs={},
            collection_mode=runtime_config.REMOTE_DB_ONLY_COLLECTION_MODE,
            duration_seconds=30,
            interval_seconds=15,
            output_formats="json",
            content_validated=True,
        )
    )

    assert (out_dir / "report.json").exists()
    assert not (out_dir / "report.html").exists()


def test_collect_one_shot_writes_exact_output_files(tmp_path, monkeypatch) -> None:
    json_path = tmp_path / "fixed" / "one.json"
    html_path = tmp_path / "html" / "one.html"

    async def connect_stub(*args, **kwargs):
        return FakeConn()

    async def detect_runtime_context_stub(conn):
        return {
            "server_version_num": 180000,
            "server_version": "PostgreSQL 18",
            "current_database": "testdb",
            "current_user": "app",
            "in_recovery": False,
            "capabilities": {},
        }

    monkeypatch.setattr(collection_module, "connect", connect_stub)
    monkeypatch.setattr(collection_module, "detect_runtime_context", detect_runtime_context_stub)
    monkeypatch.setattr(
        collection_module,
        "build_plan",
        lambda *args, **kwargs: fake_plan(kwargs.get("mode"), kwargs.get("collection_mode")),
    )
    monkeypatch.setattr(collection_module, "render_html", lambda artifact, **kwargs: "<html>one-shot</html>")

    asyncio.run(
        collect_one_shot(
            content=fake_content(tmp_path),
            out_dir=tmp_path / "ignored",
            dsn=None,
            connection_kwargs={},
            collection_mode=runtime_config.REMOTE_DB_ONLY_COLLECTION_MODE,
            json_out=json_path,
            html_out=html_path,
            content_validated=True,
        )
    )

    assert json_path.exists()
    assert (
        json.loads(json_path.read_text(encoding="utf-8"))["artifact_schema_version"]
        == runtime_config.ARTIFACT_SCHEMA_VERSION
    )
    assert html_path.read_text(encoding="utf-8") == "<html>one-shot</html>"
    assert not (tmp_path / "ignored" / "report.json").exists()
    assert not (tmp_path / "ignored" / "report.html").exists()


def test_collect_one_shot_does_not_execute_or_render_planner_skipped_metric(
    tmp_path,
    monkeypatch,
) -> None:
    planned = PlannedItem(
        item_id="snapshot_charts_db.database_transaction_rate",
        section_id="snapshot_charts_db",
        item_key="database_transaction_rate",
        title="Database Transaction Rate",
        source_kind="metric",
        source_id="database.transaction_rate",
        status="skipped",
        state="expanded",
        reason="requires snapshots mode",
    )

    async def connect_stub(*args, **kwargs):
        return FakeConn()

    async def detect_runtime_context_stub(conn):
        return {
            "server_version_num": 180000,
            "server_version": "PostgreSQL 18",
            "current_database": "testdb",
            "current_user": "app",
            "in_recovery": False,
            "capabilities": {},
        }

    async def execute_report_item_stub(*args, **kwargs):
        pytest.fail("a planner-skipped metric must not be executed")

    monkeypatch.setattr(collection_module, "connect", connect_stub)
    monkeypatch.setattr(collection_module, "detect_runtime_context", detect_runtime_context_stub)
    monkeypatch.setattr(collection_module, "execute_report_item", execute_report_item_stub)
    monkeypatch.setattr(
        collection_module,
        "build_plan",
        lambda *args, **kwargs: fake_plan_with_items(
            kwargs.get("mode"),
            kwargs.get("collection_mode"),
            [planned],
        ),
    )
    monkeypatch.setattr(collection_module, "render_html", lambda artifact, **kwargs: "<html></html>")

    progress_output = StringIO()
    progress = ProgressReporter(tmp_path / "out" / "report.log", stream=progress_output)
    try:
        artifact = asyncio.run(
            collect_one_shot(
                content=fake_content(tmp_path),
                out_dir=tmp_path / "out",
                dsn=None,
                connection_kwargs={},
                collection_mode=runtime_config.REMOTE_DB_ONLY_COLLECTION_MODE,
                content_validated=True,
                progress=progress,
            )
        )
    finally:
        progress.close()

    assert artifact["items"] == {}
    assert artifact["sections"] == []
    assert (
        "progress=100% SKIP "
        "item=snapshot_charts_db.database_transaction_rate reason=requires snapshots mode"
    ) in progress_output.getvalue()


def test_collect_one_shot_rejects_unknown_item_before_connecting(tmp_path, monkeypatch) -> None:
    async def connect_stub(*args, **kwargs):
        pytest.fail("database connection must not be opened for an unknown item")

    monkeypatch.setattr(collection_module, "connect", connect_stub)

    with pytest.raises(ValueError, match=r"Unknown report item: overview\.missing"):
        asyncio.run(
            collect_one_shot(
                content=fake_content(tmp_path),
                out_dir=tmp_path / "out",
                dsn=None,
                connection_kwargs={},
                content_validated=True,
                item_id="overview.missing",
            )
        )

    assert not (tmp_path / "out" / "report.json").exists()
    assert not (tmp_path / "out" / "report.html").exists()


def test_collect_snapshots_writes_exact_output_files(tmp_path, monkeypatch) -> None:
    json_path = tmp_path / "fixed" / "many.json"
    html_path = tmp_path / "html" / "many.html"

    import pg_diag.snapshots as snapshots_module

    async def connect_stub(*args, **kwargs):
        return FakeConn()

    async def detect_runtime_context_stub(conn):
        return {
            "server_version_num": 180000,
            "server_version": "PostgreSQL 18",
            "current_database": "testdb",
            "current_user": "app",
            "in_recovery": False,
            "capabilities": {},
        }

    async def collect_db_samples_stub(*args, **kwargs):
        return [], [], {}

    monkeypatch.setattr(collection_module, "connect", connect_stub)
    monkeypatch.setattr(collection_module, "detect_runtime_context", detect_runtime_context_stub)
    monkeypatch.setattr(snapshots_module, "_collect_db_samples", collect_db_samples_stub)
    monkeypatch.setattr(
        collection_module,
        "build_plan",
        lambda *args, **kwargs: fake_plan(kwargs.get("mode"), kwargs.get("collection_mode")),
    )
    monkeypatch.setattr(collection_module, "render_html", lambda artifact, **kwargs: "<html>snapshots</html>")

    asyncio.run(
        collect_snapshots(
            content=fake_content(tmp_path),
            out_dir=tmp_path / "ignored",
            dsn=None,
            connection_kwargs={},
            collection_mode=runtime_config.REMOTE_DB_ONLY_COLLECTION_MODE,
            duration_seconds=30,
            interval_seconds=15,
            json_out=json_path,
            html_out=html_path,
            content_validated=True,
        )
    )

    assert json_path.exists()
    assert html_path.read_text(encoding="utf-8") == "<html>snapshots</html>"
    assert not (tmp_path / "ignored" / "report.json").exists()
    assert not (tmp_path / "ignored" / "report.html").exists()


def test_collect_snapshots_omits_remote_skipped_once_items(tmp_path, monkeypatch) -> None:
    import pg_diag.snapshots as snapshots_module

    planned = PlannedItem(
        item_id="os.kernel_version",
        section_id="os",
        item_key="kernel_version",
        title="Kernel Version",
        source_kind="script",
        status="skipped",
        state="expanded",
        reason="no data because remote call",
        source_id="os.kernel_version",
        script_file="os/kernel_version.sh",
        collection_scope="once",
    )

    async def connect_stub(*args, **kwargs):
        return FakeConn()

    async def detect_runtime_context_stub(conn):
        return {
            "server_version_num": 180000,
            "server_version": "PostgreSQL 18",
            "current_database": "testdb",
            "current_user": "app",
            "in_recovery": False,
            "capabilities": {},
        }

    async def collect_db_samples_stub(*args, **kwargs):
        return [], [], {}

    async def execute_report_item_stub(*args, **kwargs):
        pytest.fail("a planner-skipped item must not be executed")

    monkeypatch.setattr(collection_module, "connect", connect_stub)
    monkeypatch.setattr(collection_module, "detect_runtime_context", detect_runtime_context_stub)
    monkeypatch.setattr(collection_module, "execute_report_item", execute_report_item_stub)
    monkeypatch.setattr(snapshots_module, "_collect_db_samples", collect_db_samples_stub)
    monkeypatch.setattr(
        collection_module,
        "build_plan",
        lambda *args, **kwargs: fake_plan_with_items(
            kwargs.get("mode"),
            kwargs.get("collection_mode"),
            [planned],
        ),
    )
    monkeypatch.setattr(collection_module, "render_html", lambda artifact, **kwargs: "<html>snapshots</html>")

    progress_output = StringIO()
    progress = ProgressReporter(tmp_path / "out" / "report.log", stream=progress_output)
    try:
        artifact = asyncio.run(
            collect_snapshots(
                content=fake_content(tmp_path),
                out_dir=tmp_path / "out",
                dsn=None,
                connection_kwargs={},
                collection_mode=runtime_config.REMOTE_DB_ONLY_COLLECTION_MODE,
                duration_seconds=30,
                interval_seconds=15,
                content_validated=True,
                progress=progress,
            )
        )
    finally:
        progress.close()

    assert "os.kernel_version" not in artifact["items"]
    assert artifact["sections"] == []
    log_text = (tmp_path / "out" / "report.log").read_text(encoding="utf-8")
    assert "progress=100% SKIP item=os.kernel_version reason=no data because remote call" in log_text
    assert progress_output.getvalue() == log_text
    assert (tmp_path / "out" / "report.log").stat().st_mode & 0o777 == 0o600


def test_collect_snapshots_skips_empty_window_for_requested_once_item(
    tmp_path,
    monkeypatch,
) -> None:
    import pg_diag.snapshots as snapshots_module

    planned = PlannedItem(
        item_id="overview.pg_settings",
        section_id="overview",
        item_key="pg_settings",
        title="PostgreSQL Settings",
        source_kind="query",
        source_id="cluster.settings",
        status="planned",
        state="expanded",
        collection_scope="once",
    )
    plan = fake_plan_with_items(
        runtime_config.SNAPSHOTS_MODE,
        runtime_config.REMOTE_DB_ONLY_COLLECTION_MODE,
        [planned],
    )
    calls: list[str] = []

    async def connect_stub(*args, **kwargs):
        return FakeConn()

    async def detect_runtime_context_stub(conn):
        return {
            "server_version_num": 180000,
            "server_version": "PostgreSQL 18",
            "current_database": "testdb",
            "current_user": "app",
            "in_recovery": False,
            "capabilities": {},
        }

    async def execute_once_stub(content, conn, item, ssh, database_connector):
        calls.append(f"once:{item.item_id}")
        return item_from_plan(item, collection_status="ok", result={"kind": "none"})

    async def collect_db_samples_stub(*args, **kwargs):
        pytest.fail("snapshot window must not start for a requested once item")

    content = fake_content(tmp_path)
    content.report["sections"] = {
        "overview": {
            "title": "Overview",
            "items": {"pg_settings": {"query": "cluster.settings"}},
        }
    }
    monkeypatch.setattr(collection_module, "connect", connect_stub)
    monkeypatch.setattr(collection_module, "detect_runtime_context", detect_runtime_context_stub)
    monkeypatch.setattr(collection_module, "build_plan", lambda *args, **kwargs: plan)
    monkeypatch.setattr(collection_module, "execute_report_item", execute_once_stub)
    monkeypatch.setattr(snapshots_module, "_collect_db_samples", collect_db_samples_stub)
    monkeypatch.setattr(collection_module, "render_html", lambda artifact, **kwargs: "<html></html>")

    artifact = asyncio.run(
        collect_snapshots(
            content=content,
            out_dir=tmp_path / "out",
            dsn=None,
            connection_kwargs={},
            collection_mode=runtime_config.REMOTE_DB_ONLY_COLLECTION_MODE,
            duration_seconds=30,
            interval_seconds=15,
            content_validated=True,
            item_id=planned.item_id,
        )
    )

    assert calls == ["once:overview.pg_settings"]
    assert artifact["snapshots"] == []
    assert artifact["runtime"]["snapshot_count"] == 0
    assert "snapshot_window_started_at" not in artifact["runtime"]
    assert "snapshot_window_finished_at" not in artifact["runtime"]


def test_collect_snapshots_runs_static_items_before_chart_window(tmp_path, monkeypatch) -> None:
    import pg_diag.snapshots as snapshots_module

    static_item = PlannedItem(
        item_id="overview.pg_settings",
        section_id="overview",
        item_key="pg_settings",
        title="PostgreSQL Settings",
        source_kind="query",
        source_id="cluster.settings",
        status="planned",
        state="expanded",
        collection_scope="once",
    )
    chart_source = SourceJob(
        job_id="metrics.chart",
        title="Chart source",
        source_id="metrics.chart",
        status="planned",
        collection_scope="every_snapshot",
    )
    endpoint_source = SourceJob(
        job_id="metrics.delta",
        title="Delta source",
        source_id="metrics.delta",
        status="planned",
        collection_scope="window_endpoints",
    )
    plan = SimpleNamespace(
        mode=runtime_config.SNAPSHOTS_MODE,
        collection_mode=runtime_config.REMOTE_DB_ONLY_COLLECTION_MODE,
        server_version_num=180000,
        supported_server_version=True,
        reason=None,
        sections=[
            {
                "section_id": "overview",
                "title": "Overview",
                "state": "expanded",
                "items": [static_item.item_id],
            }
        ],
        items=[static_item],
        source_jobs=[chart_source, endpoint_source],
    )
    call_order = []

    async def connect_stub(*args, **kwargs):
        return FakeConn()

    async def detect_runtime_context_stub(conn):
        return {
            "server_version_num": 180000,
            "server_version": "PostgreSQL 18",
            "current_database": "testdb",
            "current_user": "app",
            "in_recovery": False,
            "capabilities": {},
        }

    async def execute_once_stub(content, conn, planned, ssh, database_connector):
        assert ssh is None
        assert database_connector.connection_kwargs == {
            "server_settings": {
                "statement_timeout": "10000",
                "lock_timeout": "1000",
                "idle_in_transaction_session_timeout": "10000",
                "search_path": "pg_catalog, public",
            }
        }
        call_order.append(f"once:{planned.item_id}")
        return item_from_plan(planned, collection_status="ok", result={"kind": "none"})

    async def collect_endpoint_stub(content, conn, queries, *, phase, **kwargs):
        call_order.append(f"endpoint:{phase}")
        assert queries == [endpoint_source]
        item = item_from_plan(endpoint_source, collection_status="empty", result={"kind": "none"})
        return (
            {
                "timestamp": f"2026-07-10T00:00:0{0 if phase == 'start' else 2}+00:00",
                "items": {
                    endpoint_source.item_id: {
                        "collection_status": "empty",
                        "result": {"kind": "none"},
                    }
                },
            },
            [],
            {endpoint_source.item_id: item},
        )

    async def collect_db_samples_stub(content, conn, queries, *args, **kwargs):
        call_order.append("chart-window")
        assert queries == [chart_source]
        item = item_from_plan(chart_source, collection_status="empty", result={"kind": "none"})
        return (
            [
                {
                    "timestamp": "2026-07-10T00:00:01+00:00",
                    "items": {
                        chart_source.item_id: {
                            "collection_status": "empty",
                            "result": {"kind": "none"},
                        }
                    },
                }
            ],
            [],
            {chart_source.item_id: item},
        )

    content = fake_content(tmp_path)
    content.report["runtime_policy"] = {
        "fail_fast": False,
        "query_text_catalog": {
            "id_column_suffix": "query_id",
            "value_column_remove_suffix": "_id",
        },
    }
    content.metrics = {}
    monkeypatch.setattr(collection_module, "connect", connect_stub)
    monkeypatch.setattr(collection_module, "detect_runtime_context", detect_runtime_context_stub)
    monkeypatch.setattr(collection_module, "build_plan", lambda *args, **kwargs: plan)
    monkeypatch.setattr(collection_module, "execute_report_item", execute_once_stub)
    monkeypatch.setattr(snapshots_module, "_collect_window_endpoint", collect_endpoint_stub)
    monkeypatch.setattr(snapshots_module, "_collect_db_samples", collect_db_samples_stub)
    monkeypatch.setattr(collection_module, "render_html", lambda artifact, **kwargs: "<html></html>")

    artifact = asyncio.run(
        collect_snapshots(
            content=content,
            out_dir=tmp_path / "out",
            dsn=None,
            connection_kwargs={},
            collection_mode=runtime_config.REMOTE_DB_ONLY_COLLECTION_MODE,
            duration_seconds=30,
            interval_seconds=15,
            content_validated=True,
        )
    )

    assert call_order == [
        "once:overview.pg_settings",
        "endpoint:start",
        "chart-window",
        "endpoint:end",
    ]
    assert set(artifact["items"]) == {"overview.pg_settings"}
    assert isinstance(artifact["items"]["overview.pg_settings"]["collected_at"], str)
    assert artifact["items"]["overview.pg_settings"]["collected_at"]
    assert set(artifact["snapshots"][0]["items"]) == {chart_source.item_id}
    assert artifact["runtime"]["once_item_count"] == 1
    assert artifact["runtime"]["chart_queries_per_sample"] == 1
    assert artifact["runtime"]["window_endpoint_query_count"] == 1


def test_collect_snapshots_uses_backend_proc_window_endpoints(tmp_path, monkeypatch) -> None:
    import pg_diag.snapshots as snapshots_module

    metric_item = PlannedItem(
        item_id="backend_os.backend_proc_cpu",
        section_id="backend_os",
        item_key="backend_proc_cpu",
        title="PostgreSQL Backend /proc CPU",
        source_kind="metric",
        source_id="backend.proc_cpu_top",
        status="planned",
        state="expanded",
        collection_scope="window_endpoints",
        source_metadata={"source_sampler": "os.backend_proc"},
    )
    plan = fake_plan_with_items(
        runtime_config.SNAPSHOTS_MODE,
        runtime_config.LOCAL_COLLECTION_MODE,
        [metric_item],
    )
    call_order = []
    endpoint_samples = [{"timestamp": "end", "rows": [{"pid": 101, "cpu_pct": 2.5}]}]

    async def connect_stub(*args, **kwargs):
        return FakeConn()

    async def detect_runtime_context_stub(conn):
        return {
            "server_version_num": 180000,
            "server_version": "PostgreSQL 18",
            "current_database": "testdb",
            "current_user": "app",
            "in_recovery": False,
            "capabilities": {},
        }

    async def collect_db_samples_stub(*args, **kwargs):
        call_order.append("chart-window")
        return [], [], {}

    async def collect_sampler_providers_stub(*args, **kwargs):
        call_order.append("provider")
        return SamplerCollection(
            samples={"os.backend_proc": endpoint_samples},
            errors=[],
        )

    def build_metric_item_stub(planned, metric, db_snapshots, os_samples, *args):
        assert os_samples["os.backend_proc"] == endpoint_samples
        call_order.append("metric")
        return item_from_plan(planned, collection_status="ok", result={"kind": "table", "rows": []})

    content = fake_content(tmp_path)
    content.report["runtime_policy"] = {
        "fail_fast": False,
        "query_text_catalog": {
            "id_column_suffix": "query_id",
            "value_column_remove_suffix": "_id",
        },
    }
    content.metrics = {
        "backend.proc_cpu_top": {
            "source_sampler": "os.backend_proc",
            "requires_collection": "window_endpoints",
            "result": "table",
        }
    }
    source_file = tmp_path / "scripts" / "sampler.sh"
    source_file.parent.mkdir()
    source_file.write_text("#!/bin/sh\n", encoding="utf-8")
    content.sampler_providers = {
        "test_provider": {
            "module": "tests.fake_provider",
            "function": "collect",
            "grace_timeout_ms": 1000,
            "config": {},
            "outputs": {
                "os.backend_proc": {
                    "collection_scope": "window_endpoints",
                    "source_file": "sampler.sh",
                    "source_language": "bash",
                }
            },
        }
    }
    monkeypatch.setattr(collection_module, "connect", connect_stub)
    monkeypatch.setattr(collection_module, "detect_runtime_context", detect_runtime_context_stub)
    monkeypatch.setattr(collection_module, "build_plan", lambda *args, **kwargs: plan)
    monkeypatch.setattr(snapshots_module, "_collect_db_samples", collect_db_samples_stub)
    monkeypatch.setattr(
        snapshots_module,
        "collect_sampler_providers",
        collect_sampler_providers_stub,
    )
    monkeypatch.setattr(snapshots_module, "build_metric_item", build_metric_item_stub)
    monkeypatch.setattr(collection_module, "render_html", lambda artifact, **kwargs: "<html></html>")

    artifact = asyncio.run(
        collect_snapshots(
            content=content,
            out_dir=tmp_path / "out",
            dsn=None,
            connection_kwargs={},
            collection_mode=runtime_config.LOCAL_COLLECTION_MODE,
            duration_seconds=30,
            interval_seconds=15,
            content_validated=True,
        )
    )

    assert call_order == ["chart-window", "provider", "metric"]
    assert artifact["runtime"]["window_endpoint_sampler_count"] == 1


def test_collect_one_shot_rejects_unsupported_server_before_writing(tmp_path, monkeypatch) -> None:
    async def connect_stub(*args, **kwargs):
        return FakeConn()

    async def detect_runtime_context_stub(conn):
        return {
            "server_version_num": 130000,
            "current_database": "testdb",
            "in_recovery": False,
            "database_host_ip": "127.0.0.1",
        }

    unsupported_plan = fake_plan(
        runtime_config.ONE_SHOT_MODE,
        runtime_config.REMOTE_DB_ONLY_COLLECTION_MODE,
    )
    unsupported_plan.supported_server_version = False
    unsupported_plan.reason = "unsupported test version"

    monkeypatch.setattr(collection_module, "connect", connect_stub)
    monkeypatch.setattr(collection_module, "detect_runtime_context", detect_runtime_context_stub)
    monkeypatch.setattr(collection_module, "build_plan", lambda *args, **kwargs: unsupported_plan)

    with pytest.raises(UnsupportedServerVersion, match="unsupported test version"):
        asyncio.run(
            collect_one_shot(
                content=fake_content(tmp_path),
                out_dir=tmp_path / "out",
                dsn=None,
                connection_kwargs={},
                content_validated=True,
            )
        )

    assert not (tmp_path / "out" / "report.json").exists()
    assert not (tmp_path / "out" / "report.html").exists()


def test_collect_one_shot_honors_fail_fast_policy(tmp_path, monkeypatch) -> None:
    planned = PlannedItem(
        item_id="s.q",
        section_id="s",
        item_key="q",
        title="Query",
        source_kind="query",
        source_id="q",
        status="planned",
        state="expanded",
    )
    content = fake_content(tmp_path)
    content.report["runtime_policy"] = {
        "fail_fast": True,
        "query_text_catalog": {
            "id_column_suffix": "query_id",
            "value_column_remove_suffix": "_id",
        },
    }

    async def connect_stub(*args, **kwargs):
        return FakeConn()

    async def detect_runtime_context_stub(conn):
        return {
            "server_version_num": 180000,
            "current_database": "testdb",
            "in_recovery": False,
            "database_host_ip": "127.0.0.1",
        }

    async def execute_query_stub(content, conn, item):
        return item_from_plan(
            item,
            collection_status="error",
            reason="query failed",
            result={"kind": "table", "columns": [], "rows": [], "row_count": 0},
        )

    monkeypatch.setattr(collection_module, "connect", connect_stub)
    monkeypatch.setattr(collection_module, "detect_runtime_context", detect_runtime_context_stub)
    monkeypatch.setattr(
        collection_module,
        "build_plan",
        lambda *args, **kwargs: fake_plan_with_items(
            runtime_config.ONE_SHOT_MODE,
            runtime_config.REMOTE_DB_ONLY_COLLECTION_MODE,
            [planned],
        ),
    )
    monkeypatch.setattr(collection_module, "execute_query_item", execute_query_stub)

    with pytest.raises(PgDiagError, match="fail_fast stopped collection at s.q"):
        asyncio.run(
            collect_one_shot(
                content=content,
                out_dir=tmp_path / "out",
                dsn=None,
                connection_kwargs={},
                content_validated=True,
            )
        )

    assert not (tmp_path / "out" / "report.json").exists()
