"""Phase orchestration tests: runtime marker statuses and local end-to-end."""

from __future__ import annotations

import asyncio
import csv
from datetime import datetime, timedelta, timezone
import io
import json
from types import SimpleNamespace

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
    query_text = "select 'do-not-retain' /* " + ("x" * 9_000) + " */"
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
        async def run_script_bytes(self, script, *, arguments=(), timeout):
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


def test_phase_truncated_window_makes_counts_lower_bounds(tmp_path) -> None:
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

        return await original_scan(self, dc_replace(request, scan_budget_bytes=32 * 1024))

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
