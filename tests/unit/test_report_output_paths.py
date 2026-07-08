from __future__ import annotations

import asyncio
from types import SimpleNamespace

from pg_diag import runtime_config
from pg_diag.artifact import report_output_paths
from pg_diag.planner import PlannedItem
from pg_diag.snapshot import collect_snapshot
from pg_diag.snapshots import collect_snapshots


class FakeConn:
    async def close(self) -> None:
        pass


def fake_content(tmp_path):
    return SimpleNamespace(
        path=tmp_path,
        report={"report": {"id": "test", "title": "Test"}, "sections": {}},
        checksum="sha256:test",
    )


def fake_plan(mode: str, collection_mode: str):
    return SimpleNamespace(
        mode=mode,
        collection_mode=collection_mode,
        server_version_num=180000,
        sections=[],
        items=[],
    )


def fake_plan_with_items(mode: str, collection_mode: str, items):
    return SimpleNamespace(
        mode=mode,
        collection_mode=collection_mode,
        server_version_num=180000,
        sections=[{"section_id": "os", "title": "OS", "items": [item.item_id for item in items]}],
        items=items,
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


def test_collect_snapshot_writes_exact_output_files(tmp_path, monkeypatch) -> None:
    json_path = tmp_path / "fixed" / "one.json"
    html_path = tmp_path / "html" / "one.html"

    import pg_diag.snapshot as snapshot_module

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

    monkeypatch.setattr(snapshot_module, "validate_content", lambda content: [])
    monkeypatch.setattr(snapshot_module, "connect", connect_stub)
    monkeypatch.setattr(snapshot_module, "detect_runtime_context", detect_runtime_context_stub)
    monkeypatch.setattr(
        snapshot_module,
        "build_plan",
        lambda content, server_version_num, mode, collection_mode: fake_plan(mode, collection_mode),
    )
    monkeypatch.setattr(snapshot_module, "render_html", lambda artifact: "<html>snapshot</html>")

    asyncio.run(
        collect_snapshot(
            content=fake_content(tmp_path),
            out_dir=tmp_path / "ignored",
            dsn=None,
            connection_kwargs={},
            collection_mode=runtime_config.REMOTE_DB_ONLY_COLLECTION_MODE,
            json_out=json_path,
            html_out=html_path,
        )
    )

    assert json_path.exists()
    assert html_path.read_text(encoding="utf-8") == "<html>snapshot</html>"
    assert not (tmp_path / "ignored" / "report.json").exists()
    assert not (tmp_path / "ignored" / "report.html").exists()


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
        return [], []

    monkeypatch.setattr(snapshots_module, "validate_content", lambda content: [])
    monkeypatch.setattr(snapshots_module, "connect", connect_stub)
    monkeypatch.setattr(snapshots_module, "detect_runtime_context", detect_runtime_context_stub)
    monkeypatch.setattr(snapshots_module, "_collect_db_samples", collect_db_samples_stub)
    monkeypatch.setattr(
        snapshots_module,
        "build_plan",
        lambda content, server_version_num, mode, collection_mode: fake_plan(mode, collection_mode),
    )
    monkeypatch.setattr(snapshots_module, "render_html", lambda artifact: "<html>snapshots</html>")

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
        )
    )

    assert json_path.exists()
    assert html_path.read_text(encoding="utf-8") == "<html>snapshots</html>"
    assert not (tmp_path / "ignored" / "report.json").exists()
    assert not (tmp_path / "ignored" / "report.html").exists()


def test_collect_snapshots_formats_remote_skipped_once_items(tmp_path, monkeypatch) -> None:
    import pg_diag.snapshots as snapshots_module

    planned = PlannedItem(
        item_id="os.kernel_version",
        section_id="os",
        item_key="kernel_version",
        title="Kernel Version",
        source_kind="script",
        status="skipped",
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
        return [], []

    monkeypatch.setattr(snapshots_module, "validate_content", lambda content: [])
    monkeypatch.setattr(snapshots_module, "connect", connect_stub)
    monkeypatch.setattr(snapshots_module, "detect_runtime_context", detect_runtime_context_stub)
    monkeypatch.setattr(snapshots_module, "_collect_db_samples", collect_db_samples_stub)
    monkeypatch.setattr(
        snapshots_module,
        "build_plan",
        lambda content, server_version_num, mode, collection_mode: fake_plan_with_items(
            mode,
            collection_mode,
            [planned],
        ),
    )
    monkeypatch.setattr(snapshots_module, "render_html", lambda artifact: "<html>snapshots</html>")

    artifact = asyncio.run(
        collect_snapshots(
            content=fake_content(tmp_path),
            out_dir=tmp_path / "out",
            dsn=None,
            connection_kwargs={},
            collection_mode=runtime_config.REMOTE_DB_ONLY_COLLECTION_MODE,
            duration_seconds=30,
            interval_seconds=15,
        )
    )

    item = artifact["items"]["os.kernel_version"]
    assert item["collection_status"] == "skipped"
    assert item["reason"] == "remote_db_only"
    assert item["result"] == {"kind": "plain_text", "data": "no data because remote call"}
