from __future__ import annotations

import os
import subprocess
import sys
import json
from pathlib import Path


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
    assert "no data bacause remote call" in proc.stdout


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
    assert "variant_id=database_stats_pg15_plus" in proc.stdout
    assert "pg_stat_database" in proc.stdout


def test_render_from_json_cli(repo_root: Path, tmp_path: Path) -> None:
    artifact = {
        "artifact_schema_version": 1,
        "generator": {"name": "pg_diag", "version": "0.8.0"},
        "content": {"schema_version": 2, "checksum": "sha256:test"},
        "report": {"id": "test", "title": "Test Report"},
        "runtime": {
            "mode": "snapshot",
            "collection_mode": "remote-db-only",
            "server_version_num": 180000,
            "started_at": "2026-07-04T00:00:00Z",
        },
        "sections": [{"section_id": "overview", "title": "Overview", "items": ["overview.x"]}],
        "items": {
            "overview.x": {
                "item_id": "overview.x",
                "section_id": "overview",
                "title": "X",
                "source_kind": "query",
                "collection_status": "ok",
                "severity_level": "unknown",
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
            }
        },
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
