from __future__ import annotations

import os
import subprocess
import sys
import json
from pathlib import Path
import shutil

import pytest

from pg_diag import runtime_config
from pg_diag.cli import build_parser


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
    proc = run_cli(repo_root, "validate")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "OK content=" in proc.stdout


def test_bundled_content_default_is_independent_of_working_directory(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(repo_root)

    proc = subprocess.run(
        [sys.executable, "-m", "pg_diag.cli", "validate"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert f"OK content={repo_root / 'pg_diag' / 'content'}" in proc.stdout


def test_validate_cli_reports_content_integrity_failure_to_both_streams(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    copied = tmp_path / "content"
    shutil.copytree(repo_root / "pg_diag" / "content", copied)
    report = copied / "report.yaml"
    report.write_text(report.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")

    proc = run_cli(repo_root, "validate", "--content", str(copied))

    assert proc.returncode == 2
    assert "CRITICAL: content integrity verification failed." in proc.stdout
    assert "CRITICAL: content integrity verification failed." in proc.stderr
    assert "differs from the vendor-provided pg_diag content" in proc.stdout
    assert "sha256:" not in proc.stdout
    assert "sha256:" not in proc.stderr


def test_list_queries_cli(repo_root: Path) -> None:
    proc = run_cli(repo_root, "list-queries")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "database.database_stats" in proc.stdout
    assert "database_stats_pg15_plus" in proc.stdout


def test_report_selection_cli_parses_scalar_and_array_forms() -> None:
    parser = build_parser()

    scalar = parser.parse_args(["one-shot", "--item-id", "overview.pg_settings"])
    item_array = parser.parse_args(
        [
            "one-shot",
            "--item-id=[overview.pg_settings,backend_os.postgres_main_process_linked_libraries]",
        ]
    )
    tags = parser.parse_args(["snapshots", "--tags=[security,tables]"])

    assert scalar.item_id == ("overview.pg_settings",)
    assert item_array.item_id == (
        "overview.pg_settings",
        "backend_os.postgres_main_process_linked_libraries",
    )
    assert tags.tags == ("security", "tables")


def test_output_format_cli_parses_scalar_array_and_default_forms() -> None:
    parser = build_parser()

    default = parser.parse_args(["one-shot"])
    html = parser.parse_args(["one-shot", "--output-format=html"])
    json_only = parser.parse_args(["snapshots", "--output-format=json"])
    both = parser.parse_args(["snapshots", "--output-format=[json,html]"])

    assert default.output_format == ("html", "json")
    assert html.output_format == ("html",)
    assert json_only.output_format == ("json",)
    assert both.output_format == ("html", "json")


def test_strip_meta_cli_is_opt_in_for_report_and_render_commands() -> None:
    parser = build_parser()

    assert parser.parse_args(["one-shot"]).strip_meta is False
    assert parser.parse_args(["one-shot", "--strip-meta"]).strip_meta is True
    assert parser.parse_args(["snapshots", "--strip-meta"]).strip_meta is True
    assert parser.parse_args(
        ["render", "--from-json", "report.json", "--out", "report.html", "--strip-meta"]
    ).strip_meta is True


@pytest.mark.parametrize("value", ["xml", "[html,pdf]", "[json,json]", "[]"])
def test_output_format_cli_rejects_invalid_values(value: str) -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["one-shot", f"--output-format={value}"])

    assert exc_info.value.code == 2


def test_output_format_cli_rejects_path_for_disabled_format_before_connecting(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "report"
    proc = run_cli(
        repo_root,
        "one-shot",
        "--dsn",
        "postgresql://example/db",
        "--out",
        str(out_dir),
        "--output-format=html",
        "--json-out",
        str(tmp_path / "disabled.json"),
    )

    assert proc.returncode == 2
    assert "--json-out requires --output-format to include json" in proc.stderr
    assert not out_dir.exists()


def test_report_selection_cli_rejects_item_and_tag_filter_together(repo_root: Path) -> None:
    proc = run_cli(
        repo_root,
        "one-shot",
        "--item-id=overview.pg_settings",
        "--tags=Configuration",
    )

    assert proc.returncode == 2
    assert "not allowed with argument" in proc.stderr


def test_tags_list_does_not_require_database_connection(repo_root: Path) -> None:
    proc = run_cli(repo_root, "one-shot", "--tags-list")

    assert proc.returncode == 0, proc.stderr + proc.stdout
    tags = proc.stdout.splitlines()
    assert "Security" in tags
    assert "Tables" in tags
    assert "Other" not in tags
    assert not proc.stderr


def test_item_id_list_includes_tags_and_metadata_description(repo_root: Path) -> None:
    proc = run_cli(repo_root, "snapshots", "--item-id-list")

    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert proc.stdout.startswith("ITEM_ID\tTAGS\tDESCRIPTION\n")
    assert (
        "overview.pg_settings\tConfiguration\t"
        "Runtime settings with display-friendly values where possible."
    ) in proc.stdout
    assert (
        "backend_os.postgres_main_process_linked_libraries\tProcesses,Configuration\t"
        in proc.stdout
    )
    assert not proc.stderr


def test_report_selection_cli_reports_all_unknown_item_ids_before_connecting(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "unknown-items"
    proc = run_cli(
        repo_root,
        "one-shot",
        "--dsn",
        "postgresql://example/db",
        "--item-id=[overview.missing,backend_os.missing]",
        "--out",
        str(out_dir),
    )

    assert proc.returncode == 2
    assert "Unknown report items: overview.missing, backend_os.missing" in proc.stderr
    assert not out_dir.exists()


def test_report_selection_cli_rejects_unknown_tag_before_connecting(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "unknown-tag"
    proc = run_cli(
        repo_root,
        "snapshots",
        "--dsn",
        "postgresql://example/db",
        "--tags=[Security,missing]",
        "--out",
        str(out_dir),
    )

    assert proc.returncode == 2
    assert "Unknown report tag(s): missing" in proc.stderr
    assert not out_dir.exists()


def test_explain_plan_cli(repo_root: Path) -> None:
    proc = run_cli(repo_root, "explain-plan", "--pg-version", "180000")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "wal_io_checkpoints.pg_stat_io" in proc.stdout
    assert "io_pg_stat_io_pg18_plus" in proc.stdout
    assert "no data because remote call" in proc.stdout


def test_explain_plan_defaults_to_one_shot_mode(repo_root: Path) -> None:
    proc = run_cli(
        repo_root,
        "explain-plan",
        "--pg-version",
        "180000",
        "--json",
    )

    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert json.loads(proc.stdout)["mode"] == "one-shot"


def test_legacy_snapshot_command_is_not_exposed(repo_root: Path) -> None:
    proc = run_cli(repo_root, "snapshot", "--help")

    assert proc.returncode == 2
    assert "invalid choice: 'snapshot'" in proc.stderr


def test_report_log_path_cannot_overlap_json_output(repo_root: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "report"
    proc = run_cli(
        repo_root,
        "one-shot",
        "--dsn",
        "postgresql://example/db",
        "--out",
        str(out_dir),
        "--json-out",
        str(out_dir / "report.log"),
    )

    assert proc.returncode == 2
    assert "report.log path must be different" in proc.stderr
    assert not out_dir.exists()


def test_explain_plan_remote_mode_plans_host_sources(repo_root: Path) -> None:
    proc = run_cli(
        repo_root,
        "explain-plan",
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
    proc = run_cli(repo_root, "explain-plan", "--pg-version", "130000")
    assert proc.returncode == 1
    assert "outside supported window" in proc.stdout


def test_run_query_dry_run_cli(repo_root: Path) -> None:
    proc = run_cli(
        repo_root,
        "run-query",
        "database.database_stats",
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
                "catalogs": {
                    "presentation": {"units": {"none": {}}},
                },
                "queries": {"test.query": {"title": "Embedded check query"}},
                "scripts": {},
                "metrics": {},
                "python_sources": {},
                "sampler_providers": {},
                "instructions": {
                    "overview.x": {
                        "format": "markdown",
                        "path": "instructions/items/overview/x.md",
                    }
                },
                "field_reference": {"report": "Report metadata."},
            },
            "provenance": {"report": ["report.yaml"]},
        },
        "report": {"id": "test", "title": "Test Report"},
        "runtime": {
            "mode": "one-shot",
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
                    "columns": [
                        {
                            "name": "value",
                            "label": "Value",
                            "value_kind": "text",
                            "semantic_role": "label",
                            "quantity": "text",
                            "unit": "none",
                            "quality": "exact",
                            "nullable": True,
                            "encoding": "json_string",
                        }
                    ],
                    "rows": [["</script><script>alert(1)</script>"]],
                    "row_count": 1,
                },
                "timing_ms": 1,
                "source_metadata": {
                    "query_id": "test.query",
                    "sql_file": "overview/x.sql",
                    "source_text": "select secret_check_source()",
                    "source_language": "sql",
                    "instructions": {
                        "format": "markdown",
                        "path": "instructions/items/overview/x.md",
                        "text": "Private item instruction",
                    },
                    "tags": ["SQL"],
                    "display": {"default_sort": {"column": "value", "direction": "asc"}},
                },
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

    stripped_html_path = tmp_path / "report-stripped.html"
    stripped_proc = run_cli(
        repo_root,
        "render",
        "--from-json",
        str(json_path),
        "--out",
        str(stripped_html_path),
        "--strip-meta",
    )

    assert stripped_proc.returncode == 0, stripped_proc.stderr + stripped_proc.stdout
    stripped_html = stripped_html_path.read_text(encoding="utf-8")
    assert '"strip_meta":true' in stripped_html
    assert "select secret_check_source()" not in stripped_html
    assert "Private item instruction" not in stripped_html
    assert '"queries":{}' in stripped_html
    assert '"instructions":{}' in stripped_html
    assert '"source_metadata":{"display":' in stripped_html
    assert '"tags":["SQL"]' in stripped_html


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


def test_one_shot_remote_mode_requires_explicit_ssh_identity(repo_root: Path) -> None:
    proc = run_cli(
        repo_root,
        "one-shot",
        "--dsn",
        "postgresql://app@127.0.0.1/appdb",
        "--collection-mode",
        "remote",
    )

    assert proc.returncode == 2
    assert "remote collection requires --ssh-host, --ssh-user, --ssh-key" in proc.stderr


def test_one_shot_rejects_ssh_options_outside_remote_mode(repo_root: Path) -> None:
    proc = run_cli(
        repo_root,
        "one-shot",
        "--dsn",
        "postgresql://app@127.0.0.1/appdb",
        "--collection-mode",
        "local",
        "--ssh-host",
        "db.example",
    )

    assert proc.returncode == 2
    assert "SSH options require --collection-mode remote" in proc.stderr
