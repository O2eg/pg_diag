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


def test_machine_capabilities_use_versioned_envelope(repo_root: Path) -> None:
    proc = run_cli(
        repo_root,
        "--machine",
        "--request-id=diag-capabilities",
        "--component-capabilities",
    )

    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads(proc.stdout)
    assert payload["component"] == "pg_diag"
    assert payload["request_id"] == "diag-capabilities"
    assert payload["status"] == "succeeded"
    assert payload["result"]["contract_version"] == "pg_play/component/v1"
    assert payload["result"]["capability_schema_version"] == "pg_play/capabilities/v1"
    assert (
        payload["result"]["machine_interface"]["capabilities_option"] == "--component-capabilities"
    )


def test_machine_plumbing_is_hidden_from_human_help(repo_root: Path) -> None:
    proc = run_cli(repo_root, "--help")

    assert proc.returncode == 0
    assert "--machine" not in proc.stdout
    assert "--request-id" not in proc.stdout
    assert "--component-capabilities" not in proc.stdout
    assert "validate-artifact" in proc.stdout
    assert "summarize" in proc.stdout


def test_machine_configuration_facts_classifies_invalid_report_as_validation_error(
    repo_root: Path,
) -> None:
    proc = run_cli(
        repo_root,
        "--machine",
        "--request-id=invalid-configuration-facts",
        "configuration-facts",
        "/dev/null",
    )

    payload = json.loads(proc.stdout)
    assert proc.returncode == 2
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "validation_error"


def test_bundled_content_default_is_independent_of_working_directory(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(repo_root / "src")

    proc = subprocess.run(
        [sys.executable, "-m", "pg_diag.cli", "validate"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert f"OK content={repo_root / 'src' / 'pg_diag' / 'content'}" in proc.stdout


def test_validate_cli_reports_content_integrity_failure_to_both_streams(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    copied = tmp_path / "content"
    shutil.copytree(repo_root / "src" / "pg_diag" / "content", copied)
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


def test_list_items_cli_includes_tags_as_fourth_column(repo_root: Path) -> None:
    proc = run_cli(repo_root, "list-items")

    assert proc.returncode == 0, proc.stderr + proc.stdout
    by_item_id = {
        columns[0]: columns
        for line in proc.stdout.splitlines()
        if len(columns := line.split("\t")) == 4
    }
    assert by_item_id["overview.server_version"] == [
        "overview.server_version",
        "query",
        "cluster.server_version",
        "Configuration",
    ]
    assert by_item_id["backend_os.postgres_main_process_linked_libraries"] == [
        "backend_os.postgres_main_process_linked_libraries",
        "python",
        "backend.postgres_main_process_linked_libraries",
        "Processes,Configuration",
    ]
    assert len(by_item_id) == len(proc.stdout.splitlines())
    assert not proc.stderr


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
    assert (
        parser.parse_args(
            ["render", "--from-json", "report.json", "--out", "report.html", "--strip-meta"]
        ).strip_meta
        is True
    )


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


def test_list_tags_does_not_require_database_connection(repo_root: Path) -> None:
    proc = run_cli(repo_root, "one-shot", "--list-tags")

    assert proc.returncode == 0, proc.stderr + proc.stdout
    tags = proc.stdout.splitlines()
    assert "Security" in tags
    assert "Tables" in tags
    assert "Other" not in tags
    assert not proc.stderr


def test_item_id_list_includes_tags_and_metadata_description(repo_root: Path) -> None:
    legacy = run_cli(repo_root, "snapshots", "--item-id-list")
    assert legacy.returncode == 2 and "unrecognized arguments" in legacy.stderr
    proc = run_cli(repo_root, "snapshots", "--list-item-ids")

    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert proc.stdout.startswith("ITEM_ID\tTYPE\tTAGS\tDESCRIPTION\n")
    assert (
        "overview.pg_settings\ttable\tConfiguration\t"
        "Runtime settings with display-friendly values where possible."
    ) in proc.stdout
    assert (
        "backend_os.postgres_main_process_linked_libraries\ttable\tProcesses,Configuration\t"
        in proc.stdout
    )
    assert "os.kernel_version\ttext\t" in proc.stdout
    assert "server_log.auto_explain_plans\tchart\t" in proc.stdout
    assert "snapshot_delta_workload.database_workload_delta\tdelta\t" in proc.stdout
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


def test_one_shot_host_only_item_does_not_require_database_connection(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "host-only"

    proc = run_cli(
        repo_root,
        "--machine",
        "one-shot",
        "--collection-mode",
        "local",
        "--item-id=os.kernel_version",
        "--output-format=json",
        "--out",
        str(out_dir),
    )

    assert proc.returncode == 0, proc.stderr + proc.stdout
    artifact = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    descriptor = json.loads(proc.stdout)["artifacts"][0]
    assert descriptor["schema_version"] == f"pg_diag/artifact-v{artifact['artifact_schema_version']}"
    assert artifact["runtime"]["targets"] == ["host"]
    assert artifact["runtime"]["database_connected"] is False
    assert artifact["runtime"]["server_version_num"] is None
    assert artifact["items"]["os.kernel_version"]["targets"] == ["host"]


def test_one_shot_database_item_still_requires_connection_parameters(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "db-only"

    proc = run_cli(
        repo_root,
        "one-shot",
        "--collection-mode",
        "local",
        "--item-id=overview.pg_settings",
        "--out",
        str(out_dir),
    )

    assert proc.returncode == 2
    assert "selected items require database connection" in proc.stderr
    assert "overview.pg_settings" in proc.stderr
    assert not out_dir.exists()


def test_remote_host_only_item_requires_ssh_but_not_database_parameters(
    repo_root: Path,
) -> None:
    proc = run_cli(
        repo_root,
        "one-shot",
        "--collection-mode",
        "remote",
        "--item-id=os.kernel_version",
    )

    assert proc.returncode == 2
    assert (
        "remote collection requires --ssh-host, --ssh-user, "
        "one of --ssh-key or --ssh-agent"
    ) in proc.stderr
    assert "database connection" not in proc.stderr


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
    kernel_line = next(
        line for line in proc.stdout.splitlines() if line.startswith("os.kernel_version\t")
    )
    os_chart_line = next(
        line
        for line in proc.stdout.splitlines()
        if line.startswith("snapshot_charts_os.os_cpu_utilization\t")
    )
    assert "\tplanned\t" in kernel_line
    assert "\tplanned\t" in os_chart_line


def test_explain_plan_rejects_unsupported_pg_version(repo_root: Path) -> None:
    proc = run_cli(repo_root, "explain-plan", "--pg-version", "90000")
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
                "fallback_items": {},
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
        "object_ddl": {},
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
    assert (
        "remote collection requires --ssh-host, --ssh-user, "
        "one of --ssh-key or --ssh-agent"
    ) in proc.stderr


def test_one_shot_ssh_agent_requires_running_agent(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SSH_AUTH_SOCK", raising=False)
    proc = run_cli(
        repo_root,
        "one-shot",
        "--dsn",
        "postgresql://app@127.0.0.1/appdb",
        "--collection-mode",
        "remote",
        "--ssh-host",
        "db.example",
        "--ssh-user",
        "pgdiag",
        "--ssh-agent",
    )

    assert proc.returncode == 2
    assert "--ssh-agent requires SSH_AUTH_SOCK" in proc.stderr


def test_one_shot_rejects_key_and_agent_together(repo_root: Path) -> None:
    proc = run_cli(
        repo_root,
        "one-shot",
        "--dsn",
        "postgresql://app@127.0.0.1/appdb",
        "--collection-mode",
        "remote",
        "--ssh-host",
        "db.example",
        "--ssh-user",
        "pgdiag",
        "--ssh-key",
        "/tmp/id_ed25519",
        "--ssh-agent",
    )

    assert proc.returncode == 2
    assert "not allowed with argument --ssh-key" in proc.stderr


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


def _write_csvlog(directory: Path, name: str, rows: list[tuple[str, str, str, str]]) -> None:
    import csv
    import io

    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    for stamp, severity, sql_state, message in rows:
        writer.writerow(
            [
                stamp,
                "alice",
                "appdb",
                "42",
                "127.0.0.1:5000",
                "s",
                "7",
                "SELECT",
                "start",
                "3/44",
                "778",
                severity,
                sql_state,
                message,
                *[""] * 7,
                "loc",
                "app",
                "client backend",
                "",
                "7",
            ]
        )
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(output.getvalue(), encoding="utf-8")


def test_logs_cli_builds_server_log_report_from_directory(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    log_dir = tmp_path / "pglog"
    _write_csvlog(
        log_dir,
        "postgresql-2026-09-05_100000.csv",
        [
            ("2026-09-05 10:00:00.000 UTC", "LOG", "00000", "noise"),
            ("2026-09-05 10:05:00.000 UTC", "ERROR", "42601", "syntax error at or near X"),
            ("2026-09-05 10:05:00.000 UTC", "ERROR", "42601", "syntax error at or near X"),
            ("2026-09-05 10:06:00.000 UTC", "FATAL", "28P01", 'password authentication failed for user "bob"'),
            ("2026-09-05 10:09:00.000 UTC", "WARNING", "01000", "last warning"),
        ],
    )
    out_dir = tmp_path / "logs-report"

    proc = run_cli(
        repo_root,
        "--machine",
        "logs",
        "--log-dir",
        str(log_dir),
        "--log-depth-time-min",
        "30",
        "--out",
        str(out_dir),
    )

    assert proc.returncode == 0, proc.stderr + proc.stdout
    envelope = json.loads(proc.stdout)
    assert envelope["status"] == "succeeded"
    kinds = {item["kind"] for item in envelope["artifacts"]}
    assert kinds == {"DiagnosticReport", "DiagnosticReportHtml"}
    assert envelope["result"]["collection_mode"] == "local"
    artifact = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    runtime = artifact["runtime"]
    assert runtime["mode"] == "logs"
    assert runtime["targets"] == ["host"]
    assert runtime["database_connected"] is False
    assert runtime["server_version_num"] is None
    assert runtime["log_directory"] == str(log_dir)
    assert runtime["log_depth_time_min"] == 30
    assert runtime["ddl_extraction"] == "unavailable"
    log_collection = runtime["log_collection"]
    assert log_collection["status"] == "collected", log_collection
    assert log_collection["source"]["csv_format"]["columns"] == 26
    assert log_collection["coverage"]["requested_to"] == "2026-09-05 10:09:00.000"
    assert log_collection["coverage"]["requested_from"] == "2026-09-05 09:39:00"
    assert [section["section_id"] for section in artifact["sections"]] == ["server_log"]
    assert all(item_id.startswith("server_log.") for item_id in artifact["items"])
    chronology = artifact["items"]["server_log.error_chronology"]
    assert chronology["collection_status"] == "ok"
    assert chronology["targets"] == ["host"]
    columns = [column["name"] for column in chronology["result"]["columns"]]
    repeat_index = columns.index("repeat_count")
    assert [int(row[repeat_index]) for row in chronology["result"]["rows"]] == [1, 2]
    assert artifact["items"]["server_log.authentication_failures"]["collection_status"] == "ok"
    assert artifact["items"]["server_log.deadlock_events"]["collection_status"] == "empty"
    assert "SKIP items=" in (out_dir / "report.log").read_text(encoding="utf-8")
    assert (out_dir / "report.html").stat().st_size > 0

    validate = run_cli(repo_root, "validate-artifact", str(out_dir / "report.json"))
    assert validate.returncode == 0, validate.stderr


def test_logs_cli_rejects_invalid_arguments_before_reading_anything(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    proc = run_cli(repo_root, "logs", "--out", str(tmp_path / "x"))
    assert proc.returncode == 2 and "--log-dir" in proc.stderr

    proc = run_cli(
        repo_root, "logs", "--log-dir", str(tmp_path), "--collection-mode", "remote-db-only"
    )
    assert proc.returncode == 2 and "invalid choice" in proc.stderr

    proc = run_cli(repo_root, "logs", "--log-dir", str(tmp_path), "--log-depth-time-min", "0")
    assert proc.returncode == 2 and "positive --log-depth-time-min" in proc.stderr

    proc = run_cli(repo_root, "logs", "--log-dir", str(tmp_path), "--ssh-host", "db1")
    assert proc.returncode == 2 and "SSH options require --collection-mode remote" in proc.stderr

    proc = run_cli(repo_root, "logs", "--log-dir", "pglog", "--collection-mode", "remote")
    assert proc.returncode == 2 and "absolute path" in proc.stderr

    proc = run_cli(repo_root, "logs", "--log-dir", "/pglog", "--collection-mode", "remote")
    assert proc.returncode == 2
    assert "remote collection requires --ssh-host, --ssh-user" in proc.stderr

    proc = run_cli(
        repo_root, "logs", "--log-dir", str(tmp_path), "--item-id", "overview.pg_settings"
    )
    assert proc.returncode == 2 and "collects only server_log items" in proc.stderr
    assert not (tmp_path / "report").exists()


def test_logs_cli_reports_missing_directory_as_unavailable_section(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "logs-missing"
    proc = run_cli(
        repo_root,
        "logs",
        "--log-dir",
        str(tmp_path / "absent"),
        "--output-format",
        "json",
        "--out",
        str(out_dir),
    )
    assert proc.returncode == 0, proc.stderr
    artifact = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    marker = artifact["runtime"]["log_collection"]
    assert marker["status"] == "unavailable" and "does not exist" in marker["reason"]
    statuses = {item["collection_status"] for item in artifact["items"].values()}
    assert statuses == {"unsupported"}


def test_capabilities_and_explain_plan_expose_logs_mode(repo_root: Path) -> None:
    proc = run_cli(repo_root, "--component-capabilities")
    assert proc.returncode == 0
    assert "logs" in json.loads(proc.stdout)["commands"]
    proc = run_cli(repo_root, "explain-plan", "--pg-version", "160000", "--run-mode", "logs")
    assert proc.returncode == 0, proc.stderr
    assert "mode=logs" in proc.stdout
    planned = [line for line in proc.stdout.splitlines() if "\tplanned\t" in line]
    assert planned and all(line.startswith("server_log.") for line in planned)


def test_item_type_cli_parses_forms_and_rejects_unknown_values() -> None:
    parser = build_parser()
    assert parser.parse_args(["one-shot", "--item-type", "table"]).item_type == ("table",)
    assert parser.parse_args(["one-shot", "--item-type=[Chart,delta]"]).item_type == (
        "chart",
        "delta",
    )
    assert parser.parse_args(["logs", "--log-dir", "/x"]).item_type is None
    with pytest.raises(SystemExit):
        parser.parse_args(["one-shot", "--item-type", "graph"])


def test_item_type_filter_intersects_with_tags_and_runs_without_database(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "text-kernel"
    proc = run_cli(
        repo_root,
        "one-shot",
        "--collection-mode",
        "local",
        "--tags",
        "Kernel",
        "--item-type",
        "text",
        "--output-format",
        "json",
        "--out",
        str(out_dir),
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    artifact = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    items = artifact["items"]
    assert items and all(item_id.startswith("os.") for item_id in items)
    assert {item["item_type"] for item in items.values()} == {"text"}
    assert {item["result"]["kind"] for item in items.values()} == {"plain_text"}
    assert all("Kernel" in item["source_metadata"]["tags"] for item in items.values())
    assert all(
        diagnostic["code"] != "item_type_mismatch"
        for item in items.values()
        for diagnostic in item["diagnostics"]
    )
    assert artifact["runtime"]["database_connected"] is False
    assert "item_types=text" in (out_dir / "report.log").read_text(encoding="utf-8")


def test_item_type_selection_errors_are_reported_before_connecting(repo_root: Path) -> None:
    proc = run_cli(repo_root, "one-shot", "--item-id", "overview.pg_settings", "--item-type", "text")
    assert proc.returncode == 2
    assert "no report items match the selection" in proc.stderr
    assert "--item-id overview.pg_settings --item-type text" in proc.stderr

    proc = run_cli(repo_root, "one-shot", "--collection-mode", "local", "--item-type", "delta")
    assert proc.returncode == 2
    assert "none of the 32 selected items (--item-type delta) executes in one-shot mode" in proc.stderr
    assert "chart and delta items need snapshots" in proc.stderr

    proc = run_cli(repo_root, "one-shot", "--collection-mode", "remote-db-only", "--item-type", "text")
    assert proc.returncode == 2
    assert "executes in one-shot mode with --collection-mode remote-db-only" in proc.stderr

    proc = run_cli(repo_root, "logs", "--log-dir", "/tmp", "--item-type", "delta")
    assert proc.returncode == 2 and "logs collects only server_log items" in proc.stderr

    proc = run_cli(repo_root, "one-shot", "--item-type", "chart")
    assert proc.returncode == 2
    assert "server_log.auto_explain_plans" in proc.stderr  # the two python charts need the DB
    assert "full report" not in proc.stderr


def test_logs_cli_item_type_chart_keeps_only_python_charts(repo_root: Path, tmp_path: Path) -> None:
    log_dir = tmp_path / "pglog"
    _write_csvlog(
        log_dir,
        "postgresql-2026-09-05_100000.csv",
        [
            ("2026-09-05 10:05:00.000 UTC", "ERROR", "57014", "canceling statement due to statement timeout"),
            ("2026-09-05 10:09:00.000 UTC", "WARNING", "01000", "last warning"),
        ],
    )
    out_dir = tmp_path / "logs-charts"
    proc = run_cli(
        repo_root,
        "logs",
        "--log-dir",
        str(log_dir),
        "--item-type",
        "chart",
        "--output-format",
        "json",
        "--out",
        str(out_dir),
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    artifact = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    assert sorted(artifact["items"]) == [
        "server_log.auto_explain_plans",
        "server_log.query_termination_events",
    ]
    assert {item["item_type"] for item in artifact["items"].values()} == {"chart"}
    termination = artifact["items"]["server_log.query_termination_events"]
    assert termination["collection_status"] == "ok"
    assert termination["result"]["kind"] == "chart"
    assert termination["diagnostics"] == []


def test_logs_cli_log_timezone_resolves_named_zone_and_rejects_unknown(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    log_dir = tmp_path / "pglog"
    _write_csvlog(
        log_dir,
        "postgresql-2026-09-05_100000.csv",
        [
            ("2026-09-05 10:05:00.000 MSK", "ERROR", "57014", "canceling statement due to statement timeout"),
            ("2026-09-05 10:09:00.000 MSK", "WARNING", "01000", "last warning"),
        ],
    )
    proc = run_cli(repo_root, "logs", "--log-dir", str(log_dir), "--log-timezone", "Mars/Olympus")
    assert proc.returncode == 2 and "unknown --log-timezone" in proc.stderr

    def collect(extra: list[str], out_name: str) -> dict:
        out_dir = tmp_path / out_name
        proc = run_cli(
            repo_root,
            "logs",
            "--log-dir",
            str(log_dir),
            "--item-id",
            "server_log.query_termination_events",
            "--output-format",
            "json",
            "--out",
            str(out_dir),
            *extra,
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout
        return json.loads((out_dir / "report.json").read_text(encoding="utf-8"))

    def first_event_time(item: dict) -> str:
        series = next(entry for entry in item["result"]["series"] if entry["points"])
        return series["points"][0]["tooltip"]["log_time"]

    unknown = collect([], "unknown-zone")
    item = unknown["items"]["server_log.query_termination_events"]
    assert [d["code"] for d in item["diagnostics"]] == ["log_timezone_unknown"]
    assert "MSK" in item["diagnostics"][0]["message"]
    assert unknown["runtime"]["log_timezone"] is None
    assert first_event_time(item) == "2026-09-05T10:05:00+00:00"  # log clock shown as UTC

    resolved = collect(["--log-timezone", "Europe/Moscow"], "resolved-zone")
    item = resolved["items"]["server_log.query_termination_events"]
    assert item["diagnostics"] == []
    assert resolved["runtime"]["log_timezone"] == "Europe/Moscow"
    assert first_event_time(item) == "2026-09-05T10:05:00+03:00"
