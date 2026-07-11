from __future__ import annotations

import os
import subprocess
import sys
import json
from pathlib import Path

from pg_diag import runtime_config


def run_cli(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "pg_diag.cli", *args],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_validate_cli(repo_root: Path) -> None:
    proc = run_cli(repo_root, "validate", "--content", "content")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "OK content=" in proc.stdout


def test_list_queries_cli(repo_root: Path) -> None:
    proc = run_cli(repo_root, "list-queries", "--content", "content")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "database.database_stats" in proc.stdout
    assert "database_stats_pg15_plus" in proc.stdout


def test_explain_plan_cli(repo_root: Path) -> None:
    proc = run_cli(repo_root, "explain-plan", "--content", "content", "--pg-version", "180000")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "wal_io_checkpoints.pg_stat_io" in proc.stdout
    assert "io_pg_stat_io_pg18_plus" in proc.stdout
    assert "no data because remote call" in proc.stdout


def test_explain_plan_remote_mode_plans_host_sources(repo_root: Path) -> None:
    proc = run_cli(
        repo_root,
        "explain-plan",
        "--content",
        "content",
        "--pg-version",
        "180000",
        "--run-mode",
        "snapshots",
        "--collection-mode",
        "remote",
    )

    assert proc.returncode == 0, proc.stderr + proc.stdout
    kernel_line = next(line for line in proc.stdout.splitlines() if line.startswith("os.kernel_version\t"))
    os_chart_line = next(
        line for line in proc.stdout.splitlines()
        if line.startswith("snapshot_charts_os.os_cpu_utilization\t")
    )
    assert "\tplanned\t" in kernel_line
    assert "\tplanned\t" in os_chart_line


def test_explain_plan_rejects_unsupported_pg_version(repo_root: Path) -> None:
    proc = run_cli(repo_root, "explain-plan", "--content", "content", "--pg-version", "130000")
    assert proc.returncode == 1
    assert "outside supported window" in proc.stdout


def test_run_query_dry_run_cli(repo_root: Path) -> None:
    proc = run_cli(
        repo_root,
        "run-query",
        "database.database_stats",
        "--content",
        "content",
        "--pg-version",
        "150000",
        "--dry-run",
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "variant_id=database_stats_pg15_pg17" in proc.stdout
    assert "pg_stat_database" in proc.stdout


def test_run_query_is_always_an_inspection_command(repo_root: Path) -> None:
    proc = run_cli(
        repo_root,
        "run-query",
        "cluster.settings",
        "--content",
        "content",
        "--pg-version",
        "180000",
    )

    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "variant_id=cluster_settings_all" in proc.stdout
    assert "pg_settings" in proc.stdout


def test_render_from_json_cli(repo_root: Path, tmp_path: Path) -> None:
    artifact = {
        "artifact_schema_version": runtime_config.ARTIFACT_SCHEMA_VERSION,
        "generator": {"name": "pg_diag", "version": "0.8.0"},
        "content": {
            "schema_version": runtime_config.SUPPORTED_CONTENT_SCHEMA_VERSION,
            "content_path": "/tmp/test-content",
            "checksum": "sha256:test",
            "report_id": "test",
            "document": {
                "report": {"id": "test", "title": "Test Report"},
                "runtime_policy": {},
                "defaults": {"table": {"page_size": 25}},
                "sections": {},
                "catalogs": {},
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
        "report": {"id": "test", "title": "Test Report"},
        "runtime": {
            "mode": "snapshot",
            "collection_mode": "remote-db-only",
            "server_version_num": 180000,
            "started_at": "2026-07-04T00:00:00Z",
        },
        "display": {"table": {"page_size": 25}},
        "sections": [
            {
                "section_id": "overview",
                "title": "Overview",
                "state": "expanded",
                "items": ["overview.x"],
            }
        ],
        "items": {
            "overview.x": {
                "item_id": "overview.x",
                "section_id": "overview",
                "item_key": "x",
                "title": "X",
                "source_kind": "query",
                "collection_scope": "once",
                "collection_status": "ok",
                "severity_level": "unknown",
                "state": "expanded",
                "reason": None,
                "result": {
                    "kind": "table",
                    "columns": [{"name": "value"}],
                    "rows": [["</script><script>alert(1)</script>"]],
                    "row_count": 1,
                },
                "timing_ms": 1,
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
    json_path = tmp_path / "report.json"
    html_path = tmp_path / "report.html"
    json_path.write_text(json.dumps(artifact), encoding="utf-8")

    proc = run_cli(repo_root, "render", "--from-json", str(json_path), "--out", str(html_path))

    assert proc.returncode == 0, proc.stderr + proc.stdout
    html = html_path.read_text(encoding="utf-8")
    assert "\\u003c/script\\u003e" in html
    assert "<script>alert(1)</script>" not in html


def test_snapshots_cli_rejects_interval_below_minimum(repo_root: Path) -> None:
    proc = run_cli(
        repo_root,
        "snapshots",
        "--dsn",
        "postgresql://example/db",
        "--duration-seconds",
        "30",
        "--interval-seconds",
        "4",
    )

    assert proc.returncode == 2
    assert "between 5 and 600" in proc.stderr


def test_snapshots_cli_rejects_too_many_samples(repo_root: Path) -> None:
    proc = run_cli(
        repo_root,
        "snapshots",
        "--dsn",
        "postgresql://example/db",
        "--duration-seconds",
        "86400",
        "--interval-seconds",
        "15",
    )

    assert proc.returncode == 2
    assert "sample count 5761 exceeds maximum 300" in proc.stderr
    assert "at least 289" in proc.stderr


def test_snapshots_cli_rejects_interval_longer_than_duration(repo_root: Path) -> None:
    proc = run_cli(
        repo_root,
        "snapshots",
        "--dsn",
        "postgresql://example/db",
        "--duration-seconds",
        "30",
        "--interval-seconds",
        "600",
    )

    assert proc.returncode == 2
    assert "not greater than --duration-seconds" in proc.stderr


def test_snapshot_remote_mode_requires_explicit_ssh_identity(repo_root: Path) -> None:
    proc = run_cli(
        repo_root,
        "snapshot",
        "--dsn",
        "postgresql://app@127.0.0.1/appdb",
        "--collection-mode",
        "remote",
    )

    assert proc.returncode == 2
    assert "remote collection requires --ssh-host, --ssh-user, --ssh-key" in proc.stderr


def test_snapshot_rejects_ssh_options_outside_remote_mode(repo_root: Path) -> None:
    proc = run_cli(
        repo_root,
        "snapshot",
        "--dsn",
        "postgresql://app@127.0.0.1/appdb",
        "--collection-mode",
        "local",
        "--ssh-host",
        "db.example",
    )

    assert proc.returncode == 2
    assert "SSH options require --collection-mode remote" in proc.stderr
