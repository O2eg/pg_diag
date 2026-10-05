from __future__ import annotations

import asyncio
import csv
from dataclasses import replace
from datetime import datetime, timedelta
import io
import json
import multiprocessing
import os
from pathlib import Path
import struct
import sys
import time
from types import SimpleNamespace

import pytest

from pg_diag import artifact as artifact_module, collection, logs
from pg_diag.artifact_schema import validate_artifact
from pg_diag.cli import build_parser
from pg_diag.content_loader import load_content
from pg_diag.errors import CommandTimeoutError
from pg_diag.logscan import model, phase
from pg_diag.logscan.budget import LogValueBudget, log_payloads, retain_log_item
from pg_diag.logscan.directory import LocalLogDirectoryProbe, HarvesterLogDirectoryProbe
from pg_diag.logscan.harvester import BashHarvesterSource
from pg_diag.logscan.model import RawSeries, ScanRequest, ScanResult, ScanStats
from pg_diag.logscan.sources import LocalLogSource
from pg_diag.render.html import render_from_json


BASE = datetime(2026, 10, 2, 12)


def _raw(index: int, *, stamp: datetime | None = None, message: str | None = None) -> RawSeries:
    timestamp = (stamp or BASE + timedelta(seconds=index)).strftime("%Y-%m-%d %H:%M:%S.000 UTC")
    fields = [timestamp, "alice", "appdb", "42", "host", "session", str(index),
              "SELECT", "", "3/4", "0", "ERROR", "42601", message or f"ошибка {index}",
              "", "", "", "", "", f"SELECT 'запрос {index}'", "", "", "app",
              "client backend", "", str(index + 1)]
    output = io.StringIO()
    csv.writer(output, lineterminator="\n").writerow(fields)
    return RawSeries(file="a.csv", first_lineno=index + 1, last_lineno=index + 1, count=1,
                     first_ts=timestamp, last_ts=timestamp,
                     raw_record=output.getvalue().encode())


def _window(raw: list[RawSeries]):
    return phase._build_window(
        ScanResult(raw, ScanStats(files_seen=1, files_read=1), raw[0].first_ts, raw[-1].last_ts),
        depth_minutes=10, server_version_num=160000, window_from="2026-10-02 11:50:00",
        window_to="2026-10-02 12:10:00", locale_supported=True, encodings={},
    )


def _directory(path: Path) -> Path:
    directory = path / "pglog"
    directory.mkdir()
    (directory / "a.csv").write_bytes(b"".join(_raw(i).raw_record for i in range(4)))
    return directory


@pytest.mark.parametrize("command", ["logs", "one-shot", "snapshots"])
def test_seven_day_cli_depth(command):
    parser = build_parser()
    extra = ["--log-dir", "/tmp/pglog"] if command == "logs" else []
    assert parser.parse_args([command, *extra, "--log-depth-time-min", "10080"]).log_depth_time_min == 10080
    with pytest.raises(SystemExit) as exc:
        parser.parse_args([command, *extra, "--log-depth-time-min", "10081"])
    assert exc.value.code == 2
    assert parser.parse_args([command, *extra, "--log-depth-time-min"]).log_depth_time_min == 10


def test_budget_counts_actual_string_objects_and_refunds_replacements():
    shared = "large value " * 100
    copy = shared.encode().decode()
    assert shared == copy and shared is not copy
    value = {"ignored key" * 1000: [shared, shared, 42, None]}
    budget = LogValueBudget(100000)
    budget.add(value)
    assert budget.used == sys.getsizeof(shared)
    budget.add({"other": shared})
    budget.remove(value)
    assert budget.used == sys.getsizeof(shared)
    budget.replace({"other": shared}, [copy, "я"])
    assert budget.used == sys.getsizeof(copy) + sys.getsizeof("я")
    budget.remove([copy, "я"])
    assert budget.used == 0
    assert not budget._values


def _table_item(rows):
    return {"collection_status": "ok", "result": {
        "kind": "table", "columns": ["message"], "rows": [[row] for row in rows],
    }}


def _retain(item, budget, catalog=None, pool=None):
    retain_log_item(item, budget, catalog if catalog is not None else {}, pool or {}, {}, {})


@pytest.mark.parametrize("offset,retained", [(-1, 1), (0, 1), (1, 2)])
def test_soft_limit_keeps_whole_output_record(offset, retained):
    rows = ["first " * 100, "second " * 100, "third " * 100]
    probe = LogValueBudget(100000)
    _retain(_table_item(rows[:1]), probe)
    budget = LogValueBudget(probe.used + offset)
    item = _table_item(rows)
    _retain(item, budget)
    assert len(item["result"]["rows"]) == retained
    assert budget.hit
    assert item["result"]["budget_omitted_count"] == 3 - retained
    later = _table_item(["later"])
    _retain(later, budget)
    assert later["collection_status"] == "skipped"
    assert later["result"] == {"kind": "none"}


def test_plan_point_and_sql_are_atomic_and_unused_references_cost_nothing():
    plan = {"format": "text", "text": "Seq Scan " * 1000}
    query = "SELECT column FROM test"
    item = {"collection_status": "ok", "result": {
        "kind": "chart", "series": [{"name": "plans", "points": [
            {"value": 1, "viewer": {"plan_ref": "p1"}, "tooltip": {"query_ref": "q1"}},
            {"value": 2, "viewer": {"plan_ref": "p2"}, "tooltip": {"query_ref": "q2"}},
        ]}], "references": {"plans": {"p1": plan, "p2": {"text": "omitted" * 10000}}},
        "plan_count": 2, "displayed_plan_count": 2, "omitted_plan_count": 0,
    }}
    budget = LogValueBudget(1024)
    catalog = {"unrelated": "x" * 1000000}
    _retain(item, budget, catalog, {"q1": query, "q2": "unused SQL"})
    assert budget.hit
    assert item["result"]["references"] == {"plans": {"p1": plan}}
    assert len(item["result"]["series"][0]["points"]) == 1
    assert item["result"]["displayed_plan_count"] == 1
    assert item["result"]["omitted_plan_count"] == 1
    assert catalog == {"unrelated": "x" * 1000000, "q1": query}
    actual = LogValueBudget(100000)
    actual.add(log_payloads(item["result"]))
    actual.add(query)
    assert actual.used == budget.used


def test_log_budget_reuses_existing_sql_without_charging_unrelated_catalog():
    sql = "SELECT existing_column FROM existing_table"
    catalog = {"q1": sql, "unrelated": "x" * 100000}
    metadata = {}
    budget = LogValueBudget(10000)
    item = _table_item(["first", "second"])
    item["result"]["query_links"] = {"query_id": ["q1", "q1"]}
    retain_log_item(item, budget, catalog, {"q1": "SELECT other_sample"},
                    {"q1": {"truncated": True}}, metadata)
    assert catalog["q1"] is sql
    assert metadata == {"q1": {"representative_sample": True}}
    measured = LogValueBudget(10000)
    measured.add(log_payloads(item["result"]))
    measured.add(sql)
    assert budget.used == measured.used < 10000


def test_parser_does_not_apply_the_output_dictionary_limit(monkeypatch):
    monkeypatch.setattr(model, "REPORT_VALUE_BUDGET_BYTES", 1)
    window = _window([_raw(i) for i in range(4)])
    assert len(window.records) == 4
    assert window.coverage.ranking_complete
    assert window.coverage.estimated_value_bytes == 0


def test_late_sql_crosses_budget_and_finishes_report(content_path, tmp_path, monkeypatch):
    directory = _directory(tmp_path)
    # Use identifiers: string literals are deliberately redacted before budgeting.
    sql = "SELECT " + ", ".join(f"column_{i}" for i in range(160))
    output = io.StringIO()
    for i, query in enumerate(("", sql, "SELECT 'later'")):
        fields = next(csv.reader(io.StringIO(_raw(i).raw_record.decode())))
        fields[19], fields[25] = query, "7"
        csv.writer(output, lineterminator="\n").writerow(fields)
    (directory / "a.csv").write_text(output.getvalue())
    monkeypatch.setattr(model, "REPORT_VALUE_BUDGET_BYTES", 1024)
    artifact = asyncio.run(logs.collect_logs(
        load_content(content_path), tmp_path / "out", str(directory), 10,
        content_validated=True, output_formats=("html", "json"),
    ))
    validate_artifact(artifact)
    coverage = artifact["runtime"]["log_collection"]["coverage"]
    assert coverage["parsed_records"] == 3
    assert coverage["estimated_value_bytes"] >= len(sql.encode()) > 1024
    assert coverage["truncation_reasons"] == [model.REASON_VALUE_LIMIT]
    assert not coverage["ranking_complete"]
    assert list(artifact["query_texts"].values()) == [sql]
    saved = json.loads((tmp_path / "out/report.json").read_text())
    assert saved == artifact
    render_from_json(tmp_path / "out/report.json", tmp_path / "rerender.html")
    html = (tmp_path / "rerender.html").read_text()
    assert '"report_value_limit_hit"' in html
    assert 'id="logLimitWarning"' in html


@pytest.mark.parametrize("output_format", ["json", "html", "html,json"])
def test_limited_report_is_written_and_json_rerenders_warning(content_path, tmp_path, monkeypatch, output_format):
    directory = _directory(tmp_path)
    monkeypatch.setattr(model, "REPORT_VALUE_BUDGET_BYTES", 1)
    artifact = asyncio.run(logs.collect_logs(
        load_content(content_path), tmp_path / "out", str(directory), 10080,
        content_validated=True, output_formats=output_format.split(","), strip_meta=True,
    ))
    validate_artifact(artifact)
    coverage = artifact["runtime"]["log_collection"]["coverage"]
    assert model.REASON_VALUE_LIMIT in coverage["truncation_reasons"]
    assert coverage["requested_from"] == "2026-09-25 12:00:03"
    assert coverage["parsed_records"] == 4
    assert len(artifact["query_texts"]) == 1
    assert len(artifact["items"]) == 19
    assert sum(item["collection_status"] == "skipped" for item in artifact["items"].values()) == 18
    assert all(item["collection_status"] != "error" for item in artifact["items"].values())
    # Independently measure the returned Python graph (not a JSON reparse,
    # which cannot preserve aliases). Keys and presentation metadata are excluded.
    seen = set()
    def bytes_in(value):
        if id(value) in seen:
            return 0
        seen.add(id(value))
        if isinstance(value, str):
            return sys.getsizeof(value)
        if isinstance(value, dict):
            return sum(bytes_in(v) for v in value.values())
        if isinstance(value, (list, tuple)):
            return sum(bytes_in(v) for v in value)
        return 0
    measured = bytes_in(artifact["query_texts"])
    for item in artifact["items"].values():
        result = item["result"]
        measured += bytes_in(result.get("rows", []))
        measured += bytes_in(result.get("query_links", {}))
        measured += bytes_in(result.get("references", {}))
        for series in result.get("series", []):
            measured += bytes_in(series.get("points", []))
    assert coverage["estimated_value_bytes"] == measured
    if "json" in output_format:
        saved = json.loads((tmp_path / "out/report.json").read_text())
        assert saved == artifact
        render_from_json(tmp_path / "out/report.json", tmp_path / "rerender.html")
        assert '"report_value_limit_hit"' in (tmp_path / "rerender.html").read_text()
    if "html" in output_format:
        html = (tmp_path / "out/report.html").read_text()
        assert '"report_value_limit_hit"' in html
        assert 'id="logLimitWarning"' in html


def test_full_week_window_and_no_budget_warning(content_path, tmp_path):
    directory = _directory(tmp_path)
    old = _raw(7, stamp=BASE - timedelta(days=6))
    too_old = _raw(8, stamp=BASE - timedelta(days=8))
    path = directory / "a.csv"
    path.write_bytes(too_old.raw_record + old.raw_record + path.read_bytes())
    artifact = asyncio.run(logs.collect_logs(
        load_content(content_path), tmp_path / "out", str(directory), 10080,
        content_validated=True, output_formats="json",
    ))
    coverage = artifact["runtime"]["log_collection"]["coverage"]
    assert coverage["requested_minutes"] == 10080 and coverage["parsed_records"] == 5
    assert coverage["ranking_complete"]
    assert model.REASON_VALUE_LIMIT not in coverage["truncation_reasons"]
    assert model.WIRE_BUDGET_BYTES == 134217728


@pytest.mark.parametrize("stage", [
    "validation", "planning", "startup", "discovery", "scan", "parse",
    "catalog", "item", "item_queries", "json", "html", "cleanup",
])
def test_report_deadline_stops_blocking_work(content_path, tmp_path, monkeypatch, stage):
    content = load_content(content_path)
    directory = _directory(tmp_path)
    pid_file = tmp_path / "worker.pid"
    late_file = tmp_path / "late"

    def stalled(*args, **kwargs):
        pid_file.write_text(str(os.getpid()))
        time.sleep(10)
        late_file.write_text("background work survived")
        raise AssertionError("deadline did not interrupt blocking work")

    targets = {
        "validation": (collection, "validate_content"),
        "planning": (collection, "build_plan"),
        "startup": (collection, "create_artifact"),
        "discovery": (LocalLogDirectoryProbe, "_probe_sync"),
        "scan": (LocalLogSource, "_scan_sync"),
        "parse": (phase, "_build_window"),
        "catalog": (phase, "_finish"),
        "item_queries": (collection, "extract_item_query_texts"),
        "json": (collection, "write_json"),
        "html": (collection, "render_html"),
        "cleanup": (logs, "_remove_temporary_files"),
    }
    if stage == "item":
        async def stalled_item(*args, **kwargs):
            from pg_diag.executors.python import run_blocking
            return await run_blocking(stalled)
        monkeypatch.setattr(logs, "execute_and_record_report_item", stalled_item)
    else:
        monkeypatch.setattr(*targets[stage], stalled)
    monkeypatch.setattr(model, "LOGS_REPORT_WALLCLOCK_SECONDS", 1.0)
    monkeypatch.setattr(phase, "LOGS_FINISH_RESERVE_SECONDS", 0.3)
    before = {p.pid for p in multiprocessing.active_children()}
    started = time.monotonic()
    try:
        artifact = asyncio.run(logs.collect_logs(
            content, tmp_path / "out", str(directory), 10, content_validated=stage != "validation",
            item_id="server_log.top_errors", output_formats="json" if stage != "html" else "html",
        ))
    except CommandTimeoutError as exc:
        assert "1s deadline" in str(exc)
    else:
        # A phase deadline can leave enough time for an explicit error report.
        assert stage in {"discovery", "scan", "parse"}
        assert artifact["runtime"]["log_collection"]["status"] == "error"
    assert time.monotonic() - started < 2.0
    assert pid_file.exists(), "the targeted stage must actually have started"
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)
    assert {p.pid for p in multiprocessing.active_children()} <= before
    assert not late_file.exists()


@pytest.mark.parametrize("output_format", ["json", "html"])
@pytest.mark.parametrize("failure", ["timeout", "error"])
def test_interrupted_write_cleans_only_its_temporary_file(
    content_path, tmp_path, monkeypatch, output_format, failure,
):
    directory = _directory(tmp_path)
    output = tmp_path / "custom" / f"report.{output_format}"
    output.parent.mkdir()
    output.write_text("previous report")
    unrelated = output.with_name(f".{output.name}.another-run.tmp")
    unrelated.write_text("concurrent report")
    pid_file = tmp_path / "writer.pid"
    file_list = tmp_path / "temporary-files.json"

    def interrupted_fsync(fd):
        pid_file.write_text(str(os.getpid()))
        file_list.write_text(json.dumps([
            str(path) for path in output.parent.glob("*.tmp") if path != unrelated
        ]))
        if failure == "error":
            raise OSError("simulated fsync failure")
        time.sleep(10)
        raise AssertionError("writer survived cancellation")

    monkeypatch.setattr(artifact_module.os, "fsync", interrupted_fsync)
    monkeypatch.setattr(model, "LOGS_REPORT_WALLCLOCK_SECONDS", 2.0)
    monkeypatch.setattr(phase, "LOGS_FINISH_RESERVE_SECONDS", 0.5)
    before = {p.pid for p in multiprocessing.active_children()}
    started = time.monotonic()
    with pytest.raises(CommandTimeoutError if failure == "timeout" else RuntimeError):
        asyncio.run(logs.collect_logs(
            load_content(content_path), tmp_path / "out", str(directory), 10,
            content_validated=True, item_id="server_log.top_errors",
            output_formats=output_format, **{f"{output_format}_out": output},
        ))
    assert time.monotonic() - started < 3.0
    assert len(json.loads(file_list.read_text())) == 1, "the writer must have created a temporary file"
    assert output.read_text() == "previous report"
    assert unrelated.read_text() == "concurrent report"
    assert sorted(output.parent.iterdir()) == sorted([output, unrelated])
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)
    assert {p.pid for p in multiprocessing.active_children()} <= before


def test_remote_probe_and_harvester_share_remaining_deadline(monkeypatch):
    from pg_diag.logscan import harvester

    calls = []
    class Transport:
        async def run_script_bytes(self, script, *, timeout, output_limit_bytes):
            calls.append((script, timeout, output_limit_bytes))
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(harvester, "parse_output", lambda *args, **kwargs: ScanResult([], ScanStats()))
    deadline = time.monotonic() + 120
    asyncio.run(HarvesterLogDirectoryProbe(Transport(), deadline_monotonic=deadline)._run(
        b"probe", output_limit_bytes=1000,
    ))
    request = ScanRequest("/logs", (), "2026-10-01", "2026-10-02", (), deadline_monotonic=deadline)
    asyncio.run(BashHarvesterSource(Transport()).scan(request))
    assert all(118 < timeout <= 120 for _, timeout, _ in calls)
    assert calls[1][2] == model.WIRE_BUDGET_BYTES + 1048576
    assert b"134217728" in calls[1][0]
    with pytest.raises(TimeoutError):
        asyncio.run(BashHarvesterSource(Transport()).scan(replace(request, deadline_monotonic=0)))


def test_deadline_can_interrupt_a_partially_transferred_worker_result(tmp_path, monkeypatch):
    from pg_diag.executors import python as executor

    pid_file = tmp_path / "sender.pid"
    def partial_sender(connection, function, args):
        os.setsid()
        pid_file.write_text(str(os.getpid()))
        # A header and a fragment make the pipe readable, but recv_bytes()
        # would block the parent event loop waiting for the rest of the frame.
        os.write(connection.fileno(), struct.pack("!i", 100000) + b"fragment")
        time.sleep(10)

    monkeypatch.setattr(executor, "_sync_process_entry", partial_sender)
    async def scenario():
        await asyncio.wait_for(executor.run_blocking(str, "unused"), timeout=0.2)

    started = time.monotonic()
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(scenario())
    assert time.monotonic() - started < 1.0
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


@pytest.mark.parametrize("startup_error", [False, True])
def test_deadline_bounds_ssh_cleanup_and_preserves_startup_failure(
    content_path, tmp_path, monkeypatch, startup_error,
):
    from pg_diag.ssh_transport import SshConfig

    close_started = []

    async def slow_close():
        close_started.append(True)
        await asyncio.sleep(10)

    async def connect(config):
        return SimpleNamespace(config=config, close=slow_close)

    def slow_artifact(*args):
        if startup_error:
            raise ValueError("artifact construction failed")
        time.sleep(10)

    monkeypatch.setattr(collection.SshTransport, "connect", connect)
    monkeypatch.setattr(collection, "create_artifact", slow_artifact)
    monkeypatch.setattr(model, "LOGS_REPORT_WALLCLOCK_SECONDS", 5.0 if startup_error else 1.0)

    async def scenario():
        return await asyncio.wait_for(logs.collect_logs(
            load_content(content_path), tmp_path / "out", "/logs", 10,
            collection_mode="remote", ssh_config=SshConfig(
                host="localhost", username="root", known_hosts=tmp_path / "known_hosts",
            ),
            content_validated=True, item_id="server_log.top_errors", output_formats="json",
        ), timeout=6.0 if startup_error else 2.0)

    error = ValueError if startup_error else CommandTimeoutError
    message = "artifact construction failed" if startup_error else "1s deadline"
    with pytest.raises(error, match=message):
        asyncio.run(scenario())
    assert close_started
