"""Phase orchestration tests: runtime marker statuses and local end-to-end."""

from __future__ import annotations

import asyncio
import csv
from datetime import datetime, timedelta, timezone
import io
import json
import runpy
from types import SimpleNamespace

import pytest

from pg_diag.artifact_schema import _validate_json_data
from pg_diag.logscan.model import LINE_CAP
from pg_diag.logscan.phase import collect_report_server_log


class FakeConn:
    def __init__(self, facts: dict, logdir_rows: list[dict], encodings: list[dict]):
        self._facts = facts
        self._logdir_rows = [dict(row) for row in logdir_rows]
        for row in self._logdir_rows:
            row.setdefault("in_window", True)
        self._encodings = encodings

    async def fetchrow(self, query: str, *args):
        if "count(*)" in query:
            total = sum(row["size"] for row in self._logdir_rows)
            return {"file_count": len(self._logdir_rows), "total_bytes": total}
        return self._facts

    async def fetch(self, query: str, *args):
        if "pg_ls_logdir" in query:
            return self._logdir_rows
        return self._encodings


def _run(conn, collection_mode: str = "local"):
    return SimpleNamespace(
        conn=conn,
        plan=SimpleNamespace(
            items=[SimpleNamespace(item_id="server_log.error_chronology", status="planned")]
        ),
        artifact={
            "runtime": {"database_connected": conn is not None, "collection_mode": collection_mode}
        },
    )


def _facts(tmp_path, now: datetime, **overrides):
    facts = {
        "logging_collector": "on",
        "log_destination": "stderr,csvlog",
        "log_directory": str(tmp_path),
        "data_directory": "/pgdata",
        "lc_messages": "C",
        "server_version_num": 160000,
        "current_csvlog": "log/a.csv",
        "log_rotation_age": "1d",
        "log_rotation_size": "10MB",
        "log_truncate_on_rotation": "off",
        "log_filename": "postgresql-%Y-%m-%d_%H%M%S.log",
        "window_from": (now - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S"),
        "window_to": now.strftime("%Y-%m-%d %H:%M:%S"),
    }
    facts.update(overrides)
    return facts


def _record(ts: datetime, severity: str, message: str) -> str:
    stamp = ts.strftime("%Y-%m-%d %H:%M:%S.000 UTC")
    return (
        f"{stamp},alice,appdb,42,c,s,7,SELECT,start,3/44,778,"
        f"{severity},42601,{message},,,,,,,,loc,app,client backend,,7\n"
    )


def test_phase_skipped_without_flag() -> None:
    run = _run(None)
    window = asyncio.run(collect_report_server_log(run, depth_minutes=None))
    assert window is None
    marker = run.artifact["runtime"]["log_collection"]
    assert marker["status"] == "skipped"
    run = _run(None)
    asyncio.run(collect_report_server_log(run, depth_minutes=0))
    assert run.artifact["runtime"]["log_collection"]["status"] == "skipped"


def test_phase_preserves_numeric_events_and_query_identity(tmp_path) -> None:
    now = datetime(2026, 8, 31, 10, 30)
    messages = [
        "duration: 20.161 ms  statement: SELECT pg_sleep(0.02)",
        "duration: 201.236 ms  statement: SELECT pg_sleep(0.2)",
        "duration: 601.729 ms  statement: SELECT pg_sleep(0.6)",
        'temporary file: path "base/pgsql_tmp/pgsql_tmp42.1", size 2752512',
        'temporary file: path "base/pgsql_tmp/pgsql_tmp42.0", size 280000',
        'temporary file: path "base/pgsql_tmp/pgsql_tmp42.3", size 13672448',
        'temporary file: path "base/pgsql_tmp/pgsql_tmp42.2", size 1400000',
        "invalid record length at 0/5E15058: expected at least 24, got 0",
        "invalid record length at 0/5E15058: expected at least 24, got 12",
    ]
    output = io.StringIO()
    for i, message in enumerate(messages):
        row = next(
            csv.reader(io.StringIO(_record(now - timedelta(seconds=20 - i), "LOG", "placeholder")))
        )
        row[12] = "00000"
        row[13] = message
        row[22] = f"app{i % 2}"
        row[25] = str(i + 1)
        csv.writer(output, lineterminator="\n").writerow(row)
    path = tmp_path / "a.csv"
    path.write_text(output.getvalue())
    conn = FakeConn(
        _facts(tmp_path, now),
        [
            {
                "name": path.name,
                "size": path.stat().st_size,
                "modification": now.replace(tzinfo=timezone.utc),
            }
        ],
        [],
    )
    run = _run(conn)
    run.plan.items = [
        SimpleNamespace(item_id=item_id, status="planned")
        for item_id in ("server_log.query_resource_events", "server_log.system_incidents")
    ]
    window = asyncio.run(collect_report_server_log(run, depth_minutes=10))
    assert [record.message for record in window.records] == messages
    assert [record.repeat_count for record in window.records] == [1] * len(messages)
    assert [record.query_id for record in window.records] == list(range(1, len(messages) + 1))
    assert [record.application_name for record in window.records] == [
        f"app{i % 2}" for i in range(len(messages))
    ]
    assert all(record.count_complete for record in window.records)
    coverage = run.artifact["runtime"]["log_collection"]["coverage"]
    assert coverage["requested_from"] == "2026-08-31 10:20:00"
    assert coverage["requested_to"] == "2026-08-31 10:30:00"


def test_phase_skipped_when_no_server_log_items_selected() -> None:
    run = _run(None)
    run.plan.items[0] = SimpleNamespace(item_id="overview.server_version", status="planned")
    asyncio.run(collect_report_server_log(run, depth_minutes=10))
    marker = run.artifact["runtime"]["log_collection"]
    assert marker["status"] == "skipped"
    assert "no server_log items" in marker["reason"]


def test_phase_unavailable_without_connection() -> None:
    run = _run(None)
    asyncio.run(collect_report_server_log(run, depth_minutes=10))
    marker = run.artifact["runtime"]["log_collection"]
    assert marker["status"] == "unavailable"
    assert "database connection" in marker["reason"]


def test_phase_unavailable_when_csvlog_off_keeps_inventory(tmp_path) -> None:
    now = datetime(2026, 8, 31, 10, 30)
    rows = [
        {
            "name": "old.csv",
            "size": 123,
            "modification": now.replace(tzinfo=timezone.utc),
            "in_window": False,
        }
    ]
    conn = FakeConn(_facts(tmp_path, now, log_destination="stderr"), rows, [])
    run = _run(conn)
    asyncio.run(collect_report_server_log(run, depth_minutes=10))
    marker = run.artifact["runtime"]["log_collection"]
    assert marker["status"] == "unavailable"
    assert "csvlog" in marker["reason"]
    inventory = run.server_log.inventory
    assert inventory is not None
    assert inventory["files"][0]["name"] == "old.csv"
    assert inventory["settings"]["log_rotation_age"] == "1d"


def test_phase_unavailable_remote_transports(tmp_path) -> None:
    now = datetime(2026, 8, 31, 10, 30)
    rows = [
        {
            "name": "a.csv",
            "size": 10,
            "modification": now.replace(tzinfo=timezone.utc),
        }
    ]
    for mode, needle in (("remote", "SSH transport"), ("remote-db-only", "local or remote")):
        conn = FakeConn(_facts(tmp_path, now), rows, [])
        run = _run(conn, collection_mode=mode)
        asyncio.run(collect_report_server_log(run, depth_minutes=10))
        marker = run.artifact["runtime"]["log_collection"]
        assert marker["status"] == "unavailable"
        assert needle in marker["reason"]


def test_phase_collected_local_end_to_end(tmp_path) -> None:
    now = datetime(2026, 8, 31, 10, 30)
    body = _record(now - timedelta(minutes=2), "ERROR", "unique one")
    body += "".join(
        _record(now - timedelta(minutes=1), "ERROR", "syntax error at 42") for _ in range(500)
    )
    body += _record(now - timedelta(seconds=30), "ERROR", "unique two")
    body += _record(now - timedelta(seconds=10), "LOG", "noise not recalled")
    (tmp_path / "a.csv").write_text(body)
    rows = [
        {
            "name": "a.csv",
            "size": (tmp_path / "a.csv").stat().st_size,
            "modification": now.replace(tzinfo=timezone.utc),
        }
    ]
    encodings = [{"datname": "appdb", "encoding": "UTF8"}]
    conn = FakeConn(_facts(tmp_path, now), rows, encodings)
    run = _run(conn)
    window = asyncio.run(collect_report_server_log(run, depth_minutes=10))
    marker = run.artifact["runtime"]["log_collection"]
    assert marker["status"] == "collected"
    assert window is not None
    assert [record.repeat_count for record in window.records] == [1, 500, 1]
    flood = window.records[1]
    assert flood.severity == "ERROR"
    assert flood.sql_state == "42601"
    assert flood.query_id == 7
    _validate_json_data(marker, "$", set())  # regression: no tuples in the artifact
    coverage = marker["coverage"]
    assert coverage["parsed_records"] == 3
    assert coverage["matched_lines"] == 502
    assert coverage["ranking_complete"] is True
    assert coverage["locale_supported"] is True
    assert run.server_log_window is window


def test_old_inventory_files_do_not_trigger_candidate_window_limit(tmp_path) -> None:
    now = datetime(2026, 8, 31, 10, 30)
    body = _record(now - timedelta(seconds=10), "ERROR", "current")
    (tmp_path / "current.csv").write_text(body)
    rows = [
        {
            "name": "current.csv",
            "size": (tmp_path / "current.csv").stat().st_size,
            "modification": now.replace(tzinfo=timezone.utc),
            "in_window": True,
        }
    ]
    rows.extend(
        {
            "name": f"old-{index:02d}.csv",
            "size": 10,
            "modification": (now - timedelta(days=index + 1)).replace(tzinfo=timezone.utc),
            "in_window": False,
        }
        for index in range(64)
    )
    facts = _facts(tmp_path, now, current_csvlog="log/current.csv")
    run = _run(FakeConn(facts, rows, []))

    window = asyncio.run(collect_report_server_log(run, depth_minutes=10))

    assert window is not None
    assert window.coverage.ranking_complete
    assert "candidate_limit_hit" not in window.coverage.truncation_reasons


def test_phase_keeps_lock_wait_events_distinct_and_detail_intact(tmp_path) -> None:
    now = datetime(2026, 8, 31, 10, 30)
    messages = [
        "process 10 still waiting for AccessShareLock on relation 100 of database 1 "
        "after 1000.0 ms",
        "process 20 still waiting for AccessShareLock on relation 200 of database 1 "
        "after 95000.0 ms",
        "process 30 still waiting for AccessShareLock on relation 300 of database 1 "
        "after 45000.0 ms",
    ]
    queue = ", ".join(str(pid) for pid in range(5000, 5700))
    detail = f"Process holding the lock: 4152. Wait queue: {queue}."
    body = ""
    for index, message in enumerate(messages):
        fields = [
            (now - timedelta(seconds=3 - index)).strftime("%Y-%m-%d %H:%M:%S.000 UTC"),
            "alice",
            "appdb",
            str((index + 1) * 10),
            "127.0.0.1:5000",
            "s",
            str(index + 1),
            "SELECT",
            "start",
            "3/44",
            "778",
            "LOG",
            "00000",
            message,
            detail if index == 0 else "",
            "",
            "",
            "",
            "",
            "",
            "",
            "loc",
            "app",
            "client backend",
            "",
            "7",
        ]
        output = io.StringIO()
        csv.writer(output, lineterminator="\n").writerow(fields)
        body += output.getvalue()
    (tmp_path / "a.csv").write_text(body)
    rows = [
        {
            "name": "a.csv",
            "size": (tmp_path / "a.csv").stat().st_size,
            "modification": now.replace(tzinfo=timezone.utc),
        }
    ]
    conn = FakeConn(_facts(tmp_path, now), rows, [{"datname": "appdb", "encoding": "UTF8"}])
    run = _run(conn)
    run.plan.items[0] = SimpleNamespace(item_id="server_log.lock_waits", status="planned")

    window = asyncio.run(collect_report_server_log(run, depth_minutes=10))

    assert window is not None
    assert [record.message for record in window.records] == messages
    assert len(window.records[0].detail or "") > LINE_CAP
    assert window.records[0].detail == detail


def test_phase_extracts_large_multiline_auto_explain_plan_without_query_text(tmp_path) -> None:
    now = datetime(2026, 8, 31, 10, 30)
    query_text = "select 'do-not-retain' /* " + ("x" * 90_000) + " */"
    message = "duration: 1234.5 ms  plan:\n" + json.dumps(
        {
            "Query Text": query_text,
            "Plan": {
                "Node Type": "Aggregate",
                "Plans": [{"Node Type": "Seq Scan"}],
            },
        },
        indent=2,
    )
    fields = [
        (now - timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S.000 UTC"),
        "alice",
        "appdb",
        "42",
        "c",
        "s",
        "7",
        "SELECT",
        "start",
        "3/44",
        "778",
        "WARNING",  # auto_explain.log_level is configurable
        "00000",
        message,
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "loc",
        "app",
        "client backend",
        "",
        "7",
    ]
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerow(fields)
    (tmp_path / "a.csv").write_text(output.getvalue())
    rows = [
        {
            "name": "a.csv",
            "size": (tmp_path / "a.csv").stat().st_size,
            "modification": now.replace(tzinfo=timezone.utc),
        }
    ]
    facts = _facts(
        tmp_path,
        now,
        log_timezone="UTC",
        log_utc_offset_seconds=0,
    )
    run = _run(FakeConn(facts, rows, [{"datname": "appdb", "encoding": "UTF8"}]))
    run.plan.items[0] = SimpleNamespace(item_id="server_log.auto_explain_plans", status="planned")
    run.artifact["runtime"].update({"mode": "snapshots", "interval_seconds": 5})

    window = asyncio.run(collect_report_server_log(run, depth_minutes=10))

    assert window is not None
    assert len(window.records) == 1
    plan = window.records[0].auto_explain_plan
    assert plan is not None
    assert plan.duration_ms == 1234.5
    assert plan.plan_format == "json"
    assert plan.root_node_type == "Aggregate"
    assert plan.node_count == 2
    assert plan.parsed and plan.complete
    assert plan.query_sample is not None
    assert "do-not-retain" not in plan.query_sample
    assert len(plan.query_sample) == 303
    assert plan.query_sample.endswith("...")
    assert plan.viewer_plan is not None
    assert "do-not-retain" not in plan.viewer_plan
    assert "'[LITERAL]'" in plan.viewer_plan
    assert "do-not-retain" not in window.records[0].message
    assert run.server_log.mode == "snapshots"
    assert run.server_log.interval_seconds == 5
    assert run.server_log.inventory["settings"]["log_timezone"] == "UTC"


def test_phase_collected_remote_via_local_sh(tmp_path) -> None:
    import subprocess

    class LocalShellTransport:
        async def run_script_bytes(self, script, *, arguments=(), timeout, output_limit_bytes=None):
            proc = subprocess.run(
                ["/bin/sh", "-s", "--", *arguments],
                input=script,
                capture_output=True,
                timeout=timeout,
            )
            return SimpleNamespace(
                returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
            )

    now = datetime(2026, 8, 31, 10, 30)
    body = _record(now - timedelta(minutes=2), "ERROR", "remote unique")
    body += "".join(_record(now - timedelta(minutes=1), "ERROR", "remote flood") for _ in range(50))
    (tmp_path / "a.csv").write_text(body)
    rows = [
        {
            "name": "a.csv",
            "size": (tmp_path / "a.csv").stat().st_size,
            "modification": now.replace(tzinfo=timezone.utc),
        }
    ]
    conn = FakeConn(_facts(tmp_path, now), rows, [])
    run = _run(conn, collection_mode="remote")
    run.ssh = LocalShellTransport()
    window = asyncio.run(collect_report_server_log(run, depth_minutes=10))
    assert run.artifact["runtime"]["log_collection"]["status"] == "collected"
    assert window is not None
    assert [record.repeat_count for record in window.records] == [1, 50]


def test_phase_locale_flag(tmp_path) -> None:
    now = datetime(2026, 8, 31, 10, 30)
    (tmp_path / "a.csv").write_text(_record(now - timedelta(minutes=1), "ERROR", "x"))
    rows = [
        {
            "name": "a.csv",
            "size": (tmp_path / "a.csv").stat().st_size,
            "modification": now.replace(tzinfo=timezone.utc),
        }
    ]
    conn = FakeConn(_facts(tmp_path, now, lc_messages="ru_RU.UTF-8"), rows, [])
    run = _run(conn)
    window = asyncio.run(collect_report_server_log(run, depth_minutes=10))
    assert window is not None
    assert window.coverage.locale_supported is False


@pytest.mark.parametrize("budget", ["scan_budget_bytes", "wire_budget_bytes"])
def test_phase_truncated_window_makes_counts_lower_bounds(tmp_path, content_path, budget) -> None:
    now = datetime(2026, 8, 31, 10, 30)
    body = "".join(
        _record(now - timedelta(minutes=5) + timedelta(seconds=i // 10), "ERROR", f"e {i:04d}")
        for i in range(2000)
    )
    (tmp_path / "a.csv").write_text(body)
    rows = [
        {
            "name": "a.csv",
            "size": (tmp_path / "a.csv").stat().st_size,
            "modification": now.replace(tzinfo=timezone.utc),
        }
    ]
    conn = FakeConn(_facts(tmp_path, now), rows, [])
    run = _run(conn)
    from pg_diag.logscan import model as logscan_model

    original = logscan_model.SCAN_BUDGET_BYTES
    # shrink the budget through the request path: monkeypatch ScanRequest default
    window = asyncio.run(collect_report_server_log(run, depth_minutes=10))
    assert window is not None and window.records  # full run first

    # now force truncation via a tiny scan budget
    from pg_diag.logscan.sources import LocalLogSource

    original_scan = LocalLogSource.scan

    async def tiny_budget_scan(self, request):
        from dataclasses import replace as dc_replace

        return await original_scan(self, dc_replace(request, **{budget: 32 * 1024}))

    LocalLogSource.scan = tiny_budget_scan
    try:
        run2 = _run(FakeConn(_facts(tmp_path, now), rows, []))
        window2 = asyncio.run(collect_report_server_log(run2, depth_minutes=10))
    finally:
        LocalLogSource.scan = original_scan
    assert window2 is not None
    assert window2.coverage.ranking_complete is False
    assert window2.records
    assert all(record.count_complete is False for record in window2.records)
    assert original == logscan_model.SCAN_BUDGET_BYTES
    # A bounded scan remains usable by report items; the retained evidence is
    # rendered with incomplete coverage rather than dropping the whole item.
    module = runpy.run_path(str(content_path / "python/server_log/error_chronology.py"))
    item = module["collect"](SimpleNamespace(server_log=run2.server_log))
    assert item.collection_status == "ok"
    assert item.result["rows"]
    assert "lower bounds" in item.issues["summary"]["description"]


# --- logs mode: directory discovery without a database ------------------------


def _directory_run(collection_mode: str = "local", items=("server_log.error_chronology",)):
    return SimpleNamespace(
        conn=None,
        plan=SimpleNamespace(
            items=[SimpleNamespace(item_id=item_id, status="planned") for item_id in items]
        ),
        artifact={
            "runtime": {
                "mode": "logs",
                "database_connected": False,
                "collection_mode": collection_mode,
            }
        },
    )


def _write_logs_directory(tmp_path, now: datetime) -> None:
    old = "".join(
        _record(now - timedelta(hours=3) + timedelta(seconds=i), "ERROR", f"old {i}")
        for i in range(200)
    )
    (tmp_path / "postgresql-2026-08-31_070000.csv").write_text(old)
    body = "".join(
        _record(now - timedelta(minutes=30) + timedelta(seconds=i), "LOG", "noise")
        for i in range(120)
    )
    body += _record(now - timedelta(minutes=2), "ERROR", "unique one")
    body += "".join(_record(now - timedelta(minutes=1), "ERROR", "flood 42") for _ in range(300))
    body += _record(now - timedelta(seconds=30), "ERROR", "unique two")
    body += _record(now, "WARNING", "last record")
    (tmp_path / "postgresql-2026-08-31_100000.csv").write_text(body)


def test_phase_directory_local_anchors_window_at_newest_record(tmp_path) -> None:
    now = datetime(2026, 8, 31, 10, 30)
    _write_logs_directory(tmp_path, now)
    run = _directory_run()

    window = asyncio.run(
        collect_report_server_log(run, depth_minutes=10, log_directory=str(tmp_path))
    )

    marker = run.artifact["runtime"]["log_collection"]
    assert marker["status"] == "collected", marker
    assert marker["source"]["kind"] == "directory"
    assert marker["source"]["csv_format"]["columns"] == 26
    assert marker["source"]["log_directory"] == str(tmp_path)
    _validate_json_data(marker, "$", set())
    assert window is not None
    assert [record.repeat_count for record in window.records] == [1, 300, 1]
    assert window.records[1].message == "flood 42"
    coverage = marker["coverage"]
    assert coverage["requested_from"] == "2026-08-31 10:20:00"
    assert coverage["requested_to"] == "2026-08-31 10:30:00.000"
    assert coverage["files_seen"] == 1  # the old file lies outside the window
    assert coverage["ranking_complete"] is True
    assert coverage["locale_supported"] is True
    inventory = run.server_log.inventory
    assert inventory["settings"]["log_directory"] == str(tmp_path)
    assert [row["in_window"] for row in inventory["files"]] == [True, False]
    assert inventory["files"][0]["is_newest"] is True
    assert all(row["is_current"] is False for row in inventory["files"])  # active file unknown
    assert inventory["settings"]["block_size"] is None
    assert marker["source"]["anchor_verified"] is True
    assert run.server_log.mode == "logs"


def test_phase_directory_remote_via_local_sh_matches_local(tmp_path) -> None:
    import subprocess

    class LocalShellTransport:
        async def run_script_bytes(self, script, *, arguments=(), timeout, output_limit_bytes=None):
            proc = subprocess.run(
                ["/bin/sh", "-s", "--", *arguments],
                input=script,
                capture_output=True,
                timeout=timeout,
            )
            return SimpleNamespace(
                returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
            )

    now = datetime(2026, 8, 31, 10, 30)
    _write_logs_directory(tmp_path, now)
    local_run = _directory_run()
    local = asyncio.run(
        collect_report_server_log(local_run, depth_minutes=10, log_directory=str(tmp_path))
    )
    remote_run = _directory_run(collection_mode="remote")
    remote_run.ssh = LocalShellTransport()
    remote = asyncio.run(
        collect_report_server_log(remote_run, depth_minutes=10, log_directory=str(tmp_path))
    )

    assert remote_run.artifact["runtime"]["log_collection"]["status"] == "collected"
    assert local is not None and remote is not None
    assert [(r.message, r.repeat_count) for r in remote.records] == [
        (r.message, r.repeat_count) for r in local.records
    ]
    assert remote.coverage.requested_from == local.coverage.requested_from
    assert remote.coverage.requested_to == local.coverage.requested_to
    assert remote_run.server_log.inventory["source"]["csv_format"] == (
        local_run.server_log.inventory["source"]["csv_format"]
    )


def test_phase_directory_parses_each_file_with_its_own_layout(tmp_path) -> None:
    now = datetime(2026, 8, 31, 10, 30)
    old_layout = (
        f"{(now - timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S.000 UTC')},alice,appdb,42,c,"
        "s,7,SELECT,start,3/44,778,ERROR,42601,pg12 error,,,,,,,,loc,app\n"
    )
    (tmp_path / "pg12.csv").write_text(old_layout)
    (tmp_path / "pg16.csv").write_text(_record(now, "ERROR", "pg16 error"))
    run = _directory_run()

    window = asyncio.run(
        collect_report_server_log(run, depth_minutes=10, log_directory=str(tmp_path))
    )

    assert window is not None
    by_message = {record.message: record for record in window.records}
    assert not by_message["pg12 error"].partial
    assert by_message["pg12 error"].backend_type is None
    assert by_message["pg16 error"].backend_type == "client backend"
    assert by_message["pg16 error"].query_id == 7
    columns = {row["name"]: row["csv_columns"] for row in run.server_log.inventory["files"]}
    assert columns == {"pg12.csv": 23, "pg16.csv": 26}


def test_phase_directory_unavailable_reasons(tmp_path) -> None:
    run = _directory_run()
    asyncio.run(
        collect_report_server_log(run, depth_minutes=10, log_directory=str(tmp_path / "absent"))
    )
    marker = run.artifact["runtime"]["log_collection"]
    assert marker["status"] == "unavailable" and "does not exist" in marker["reason"]

    (tmp_path / "notes.txt").write_text("no csv here")
    run = _directory_run()
    asyncio.run(collect_report_server_log(run, depth_minutes=10, log_directory=str(tmp_path)))
    marker = run.artifact["runtime"]["log_collection"]
    assert marker["status"] == "unavailable" and "no csvlog files" in marker["reason"]
    assert run.server_log.inventory["files"] == []

    now = datetime(2026, 8, 31, 10, 30)
    planted = list(csv.reader(io.StringIO(_record(now, "LOG", "placeholder"))))[0]
    planted[13] = "msg\n2027-01-01 00:00:00.000 UTC,x,y,1,c,s,7,T,st,3/4,7,LOG,00000,fake\nend"
    quoted = io.StringIO(newline="")
    csv.writer(quoted, lineterminator="\n").writerow(planted)  # message stays one quoted field
    (tmp_path / "planted.csv").write_text(
        _record(now - timedelta(minutes=3), "ERROR", "real") + quoted.getvalue()
    )
    run = _directory_run()
    window = asyncio.run(
        collect_report_server_log(run, depth_minutes=10, log_directory=str(tmp_path))
    )
    assert window is not None and [r.message for r in window.records] == ["real"]
    assert run.artifact["runtime"]["log_collection"]["coverage"]["requested_to"] == (
        "2026-08-31 10:30:00.000"
    )

    run = _directory_run(collection_mode="remote-db-only")
    asyncio.run(collect_report_server_log(run, depth_minutes=10, log_directory=str(tmp_path)))
    assert "local or remote" in run.artifact["runtime"]["log_collection"]["reason"]

    run = _directory_run(collection_mode="remote")  # no SSH transport attached
    asyncio.run(collect_report_server_log(run, depth_minutes=10, log_directory=str(tmp_path)))
    assert "SSH transport" in run.artifact["runtime"]["log_collection"]["reason"]


def test_phase_directory_inventory_only_items_skip_the_scan(tmp_path) -> None:
    now = datetime(2026, 8, 31, 10, 30)
    _write_logs_directory(tmp_path, now)
    run = _directory_run(items=("server_log.log_files_overview",))
    window = asyncio.run(
        collect_report_server_log(run, depth_minutes=10, log_directory=str(tmp_path))
    )
    assert window is not None and window.records == ()
    assert run.artifact["runtime"]["log_collection"]["coverage"]["scanned_bytes"] == 0
    assert len(run.server_log.inventory["files"]) == 2


def test_phase_directory_dst_window_and_per_record_offsets(tmp_path) -> None:
    def berlin(ts: datetime, zone: str, message: str) -> str:
        fields = [
            ts.strftime("%Y-%m-%d %H:%M:%S.000 ") + zone, "alice", "appdb", "42", "c", "s", "7",
            "SELECT", "start", "3/44", "778", "ERROR", "42601", message,
            *[""] * 7, "loc", "app", "client backend", "", "7",
        ]
        output = io.StringIO(newline="")
        csv.writer(output, lineterminator="\n").writerow(fields)
        return output.getvalue()

    (tmp_path / "a.csv").write_text(
        berlin(datetime(2026, 3, 29, 1, 58), "CET", "before switch")
        + berlin(datetime(2026, 3, 29, 3, 5), "CEST", "after switch")
    )
    run = _directory_run()
    window = asyncio.run(
        collect_report_server_log(
            run, depth_minutes=10, log_directory=str(tmp_path), log_timezone="Europe/Berlin"
        )
    )
    assert window is not None
    assert [(r.message, r.utc_offset_seconds) for r in window.records] == [
        ("before switch", 3600),
        ("after switch", 7200),
    ]
    coverage = run.artifact["runtime"]["log_collection"]["coverage"]
    assert coverage["requested_from"] == "2026-03-29 01:55:00"
    assert coverage["requested_to"] == "2026-03-29 03:05:00.000"
    assert run.server_log.inventory["settings"]["log_utc_offset_seconds"] == 7200
    assert run.server_log.inventory["settings"]["log_timezone"] == "Europe/Berlin"

    naive = _directory_run()
    asyncio.run(collect_report_server_log(naive, depth_minutes=10, log_directory=str(tmp_path)))
    assert [r.message for r in naive.server_log_window.records] == ["after switch"]  # no zone: wall clock
    assert naive.server_log_window.records[0].utc_offset_seconds is None


def _berlin_record(ts: datetime, zone: str, message: str) -> str:
    fields = [
        ts.strftime("%Y-%m-%d %H:%M:%S.000 ") + zone, "alice", "appdb", "42", "c", "s", "7",
        "SELECT", "start", "3/44", "778", "ERROR", "42601", message,
        *[""] * 7, "loc", "app", "client backend", "", "7",
    ]
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerow(fields)
    return output.getvalue()


@pytest.mark.parametrize("layout", ["same_file", "two_files"])
@pytest.mark.parametrize("collection_mode", ["local", "remote"])
def test_phase_directory_fall_back_transition_keeps_both_records(tmp_path, layout, collection_mode) -> None:
    import subprocess

    class LocalShellTransport:
        async def run_script_bytes(self, script, *, arguments=(), timeout, output_limit_bytes=None):
            proc = subprocess.run(
                ["/bin/sh", "-s", "--", *arguments], input=script, capture_output=True, timeout=timeout
            )
            return SimpleNamespace(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)

    before = _berlin_record(datetime(2026, 10, 25, 2, 58), "CEST", "before fall-back")
    after = _berlin_record(datetime(2026, 10, 25, 2, 5), "CET", "after fall-back")
    if layout == "same_file":
        (tmp_path / "a.csv").write_text(before + after)
    else:
        (tmp_path / "cest.csv").write_text(before)
        (tmp_path / "cet.csv").write_text(after)
    run = _directory_run(collection_mode=collection_mode)
    if collection_mode == "remote":
        run.ssh = LocalShellTransport()

    window = asyncio.run(
        collect_report_server_log(
            run, depth_minutes=10, log_directory=str(tmp_path), log_timezone="Europe/Berlin"
        )
    )

    assert window is not None
    assert [(r.message, r.utc_offset_seconds) for r in window.records] == [
        ("before fall-back", 7200),
        ("after fall-back", 3600),
    ]
    coverage = run.artifact["runtime"]["log_collection"]["coverage"]
    assert coverage["requested_to"] == "2026-10-25 02:05:00.000"  # the absolute-newest record
    assert coverage["requested_from"] == "2026-10-25 02:55:00"  # seven minutes earlier, still CEST
    assert coverage["ranking_complete"] is True
    source = run.artifact["runtime"]["log_collection"]["source"]
    assert source["window_scan_to"] == "2026-10-25 03:05:00.000"
    assert source["window_scan_from"] <= "2026-10-25 01:55:00"
