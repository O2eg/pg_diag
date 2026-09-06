"""Offline debugging tools must preserve inputs and work outside repo cwd."""

import csv
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools/report_debug"


def run_tool(name, *arguments, cwd):
    return subprocess.run(
        [sys.executable, str(TOOLS / name), *map(str, arguments)],
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=60,
    )


def test_graph_refresh_preserves_payload_and_crlf_outside_assets(tmp_path):
    source = tmp_path / "report.html"
    original = (
        '<!doctype html>\r\n<style id="pg-diag-graph-css">old</style>\r\n'
        '<script id="pg-diag-artifact" type="application/json">{"text":"Пример"}</script>\r\n'
        '<script id="pg-diag-graph-definition">{}</script>\r\n'
        '<script id="pg-diag-graph-library">old</script>\r\n'
        '<script id="pg-diag-graph-render-library">old</script>\r\n<footer>keep me</footer>'
    ).encode()
    source.write_bytes(original)
    output = tmp_path / "copy.html"
    completed = run_tool("refresh_html.py", source, "--output", output, cwd=tmp_path)
    assert completed.returncode == 0, completed.stderr
    assert source.read_bytes() == original
    pattern = rb'(?s)(<(?:style|script) id="pg-diag-graph-(?:css|definition|library|render-library)">).*?(</(?:style|script)>)'
    assert re.sub(pattern, rb"\1\2", output.read_bytes()) == re.sub(pattern, rb"\1\2", original)
    backup = tmp_path / "backup.html"
    completed = run_tool("refresh_html.py", source, "--backup", backup, cwd=tmp_path)
    assert completed.returncode == 0, completed.stderr
    assert backup.read_bytes() == original
    assert source.read_bytes() == output.read_bytes()
    completed = run_tool("refresh_html.py", source, "--backup", backup, cwd=tmp_path)
    assert completed.returncode != 0
    assert backup.read_bytes() == original


def test_browser_audit_rejects_output_overwriting_companion_json(tmp_path):
    source = tmp_path / "report.html"
    source.write_text("saved HTML")
    companion = source.with_suffix(".json")
    companion.write_text("original JSON")
    completed = run_tool("browser_audit.py", source, "--output", companion, cwd=tmp_path)
    assert completed.returncode != 0
    assert "Output would overwrite an input or its companion" in completed.stderr
    assert companion.read_text() == "original JSON"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is unavailable")
def test_route_debugger_cannot_overwrite_input(tmp_path):
    source = tmp_path / "report.json"
    source.write_text('{"items":{},"runtime":{}}')
    completed = subprocess.run(
        ["node", str(TOOLS / "check_routes.cjs"), str(source), str(source)],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=tmp_path,
    )
    assert completed.returncode != 0
    assert source.read_text() == '{"items":{},"runtime":{}}'


def test_saved_log_replay_compares_sources_without_fixed_counts(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "runtime": {"server_version_num": 180000},
                "items": {"server_log.top_errors": {}, "server_log.auto_explain_plans": {}},
            }
        )
    )
    logfile = tmp_path / "postgresql.csv"
    records = []
    for index, (severity, state, message) in enumerate(
        [
            ("ERROR", "23505", "duplicate key value violates unique constraint"),
            (
                "LOG",
                "00000",
                'duration: 12.000 ms  plan:\n{"Query Text":"SELECT 1","Plan":{"Node Type":"Result"}}',
            ),
        ],
        1,
    ):
        row = [""] * 26
        row[:14] = [
            f"2026-09-06 00:00:0{index}.000 UTC",
            "tester",
            "test",
            "123",
            "",
            "a.b",
            str(index),
            "SELECT",
            "2026-09-06 00:00:00 UTC",
            "1/2",
            "0",
            severity,
            state,
            message,
        ]
        records.append(row)
    with logfile.open("w", newline="") as out:
        csv.writer(out).writerows(records)
    original = logfile.read_bytes()
    output = tmp_path / "replay.json"
    completed = run_tool(
        "replay_logs.py",
        report,
        logfile,
        "--from",
        "2026-09-06 00:00:00",
        "--to",
        "2026-09-06 00:01:00",
        "--output",
        output,
        cwd=tmp_path,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    replay = json.loads(output.read_text())
    assert replay["matched"] and replay["complete"]
    for row in replay["results"]:
        assert row["plan_count"] == 1
        assert row["errors"] == {"23505": 1}
    assert logfile.read_bytes() == original
    comparison = tmp_path / "comparison.json"
    completed = run_tool(
        "compare_logs.py",
        report,
        logfile,
        "--from",
        "2026-09-06T00:00:00Z",
        "--to",
        "2026-09-06T00:01:00Z",
        "--output",
        comparison,
        cwd=tmp_path,
    )
    assert completed.returncode == 0, completed.stderr
    counted = json.loads(comparison.read_text())
    assert counted["raw_plan_count"] == 1
    assert counted["raw_error_states"] == {"23505": 1}
    assert not counted["malformed_records"]
