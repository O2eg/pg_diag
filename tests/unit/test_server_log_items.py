"""Unit tests for server_log item sources against synthetic LogWindows."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from pg_diag.logscan.model import LogCoverage, LogRecord, LogWindow
from pg_diag.logscan.rle import fingerprint

CONTENT = Path("src/pg_diag/content/python/server_log")
BASE = datetime(2026, 8, 31, 10, 0, 0)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"server_log_{name}", CONTENT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record(
    offset_s: int,
    severity: str = "ERROR",
    message: str = "boom",
    sql_state: str = "42601",
    repeat: int = 1,
    user: str = "alice",
    connection_from: str | None = "10.0.0.1:5000",
    count_complete: bool = True,
    detail: str | None = None,
) -> LogRecord:
    when = BASE + timedelta(seconds=offset_s)
    return LogRecord(
        log_time=when,
        last_time=when + timedelta(seconds=max(repeat - 1, 0)),
        repeat_count=repeat,
        severity=severity,
        sql_state=sql_state,
        message=message,
        user_name=user,
        database_name="appdb",
        process_id=42,
        connection_from=connection_from,
        backend_type="client backend",
        query_id=7,
        partial=False,
        count_complete=count_complete,
        encoding_degraded=False,
        fingerprint=fingerprint(message),
        detail=detail,
    )


def _window(records, *, ranking_complete: bool = True, locale_supported: bool = True):
    return LogWindow(
        records=tuple(records),
        coverage=LogCoverage(
            requested_minutes=10,
            covered_from="2026-08-31 09:50:00",
            covered_to="2026-08-31 10:00:00",
            files_seen=1,
            files_read=1,
            files_vanished=0,
            files_unreadable=0,
            scanned_bytes=1000,
            matched_lines=len(records),
            parsed_records=len(records),
            dropped_lines=0,
            window_truncated=not ranking_complete,
            truncation_reasons=() if ranking_complete else ("scan_limit_hit",),
            ranking_complete=ranking_complete,
            locale_supported=locale_supported,
        ),
    )


def _context(window=None, marker=None):
    if marker is None:
        marker = {"status": "collected", "reason": None, "coverage": {}}
    return SimpleNamespace(server_log=SimpleNamespace(window=window, marker=marker))


def test_status_mapping_matrix() -> None:
    module = _load("error_chronology")
    cases = [
        ({"status": "skipped", "reason": "off"}, "skipped"),
        ({"status": "unavailable", "reason": "no reader"}, "unsupported"),
        ({"status": "error", "reason": "boom"}, "error"),
    ]
    for marker, expected in cases:
        result = module.collect(_context(None, marker))
        assert result.collection_status == expected
    # unsupported locale
    window = _window([_record(1)], locale_supported=False)
    result = module.collect(_context(window))
    assert result.collection_status == "unsupported"
    assert "lc_messages" in result.reason
    # missing phase entirely
    result = module.collect(SimpleNamespace(server_log=None))
    assert result.collection_status == "error"


def test_error_chronology_orders_and_flags() -> None:
    module = _load("error_chronology")
    records = [
        _record(1, "ERROR", "unique one"),
        _record(2, "ERROR", "syntax error at N", repeat=100000),
        _record(3, "FATAL", "unique two", sql_state="57P01"),
        _record(4, "WARNING", "not an error"),
    ]
    result = module.collect(_context(_window(records)))
    assert result.collection_status == "ok"
    rows = result.result["rows"]
    columns = [c["name"] if isinstance(c, dict) else c for c in result.result["columns"]]
    by = [dict(zip(columns, row)) for row in rows] if rows and isinstance(rows[0], list) else rows
    assert len(by) == 3  # WARNING excluded
    assert by[0]["severity"] == "FATAL"  # newest first
    assert by[1]["repeat_count"] == 100000
    assert result.severity_level == "high"


def test_top_errors_aggregates_by_fingerprint() -> None:
    module = _load("top_errors")
    records = [
        _record(1, "ERROR", "dup key 1 in t1", repeat=5, user="a"),
        _record(2, "ERROR", "dup key 99 in t42", repeat=7, user="b"),
        _record(3, "FATAL", "other failure", sql_state="57P01"),
    ]
    result = module.collect(_context(_window(records)))
    rows = result.result["rows"]
    columns = [c["name"] if isinstance(c, dict) else c for c in result.result["columns"]]
    by = [dict(zip(columns, row)) for row in rows] if rows and isinstance(rows[0], list) else rows
    assert len(by) == 2  # two fingerprints share dup-key shape
    top = by[0]
    assert top["occurrences"] == 12
    assert top["distinct_users"] == 2
    assert result.severity_level == "medium"


def test_top_warnings_and_partial_coverage_note() -> None:
    module = _load("top_warnings")
    records = [_record(1, "WARNING", "checkpoints occurring too frequently", sql_state=None)]
    result = module.collect(_context(_window(records, ranking_complete=False)))
    assert result.collection_status == "ok"
    assert result.severity_level == "ok"
    assert result.issues["summary"]["title"].startswith("Top warnings cover only part")


def test_crash_recovery_events_high() -> None:
    module = _load("crash_recovery_events")
    records = [
        _record(1, "LOG", "server process (PID N) was terminated by signal 9", sql_state=None),
        _record(2, "LOG", "database system was not properly shut down", sql_state=None),
        _record(3, "ERROR", "ordinary error"),
    ]
    result = module.collect(_context(_window(records)))
    assert result.result["row_count"] == 2
    assert result.severity_level == "high"
    assert result.issues["summary"]["status"] == "fail"


def test_deadlock_events_filter() -> None:
    module = _load("deadlock_events")
    records = [
        _record(1, "ERROR", "deadlock detected", sql_state="40P01"),
        _record(2, "ERROR", "ordinary error"),
    ]
    result = module.collect(_context(_window(records)))
    assert result.result["row_count"] == 1
    assert result.severity_level == "medium"


def test_authentication_failures_grouping() -> None:
    module = _load("authentication_failures")
    records = [
        _record(1, "FATAL", 'password authentication failed for user "svc"',
                sql_state="28P01", user="svc", repeat=10,
                connection_from="10.0.0.1:50001"),
        _record(90, "FATAL", 'password authentication failed for user "svc"',
                sql_state="28P01", user="svc", repeat=5,
                connection_from="10.0.0.1:50777"),
        _record(3, "FATAL", "no pg_hba.conf entry for host", sql_state="28000",
                user="other", connection_from="10.9.9.9:1"),
        _record(4, "ERROR", "ordinary error"),
    ]
    result = module.collect(_context(_window(records)))
    rows = result.result["rows"]
    columns = [c["name"] if isinstance(c, dict) else c for c in result.result["columns"]]
    by = [dict(zip(columns, row)) for row in rows] if rows and isinstance(rows[0], list) else rows
    assert len(by) == 2
    assert by[0]["failures"] == 15  # same (user, client, db, state) merged across series
    assert by[0]["connection_from"] == "10.0.0.1"  # ephemeral port stripped
    assert result.severity_level == "medium"


def test_empty_with_incomplete_window_is_not_empty() -> None:
    module = _load("error_chronology")
    result = module.collect(_context(_window([], ranking_complete=False)))
    assert result.collection_status == "ok"
    assert result.severity_level == "unknown"
    assert "not proven" in result.issues["summary"]["description"]


def test_empty_window_is_empty_status() -> None:
    for name in (
        "error_chronology",
        "top_errors",
        "top_warnings",
        "crash_recovery_events",
        "deadlock_events",
        "authentication_failures",
    ):
        module = _load(name)
        result = module.collect(_context(_window([])))
        assert result.collection_status == "empty", name
        assert result.severity_level == "ok", name


def _by(result):
    res = result.result
    cols = [c["name"] if isinstance(c, dict) else c for c in res["columns"]]
    rows = res["rows"]
    return [dict(zip(cols, r)) for r in rows] if rows and isinstance(rows[0], list) else rows


def test_autovacuum_runs_parses_relation_and_elapsed() -> None:
    module = _load("autovacuum_runs")
    records = [
        _record(1, "LOG", 'automatic vacuum of table "appdb.public.orders": index scans: 1'),
        _record(2, "LOG",
                'automatic analyze of table "appdb.public.users" system usage: '
                "CPU: user: 0.01 s, system: 0.00 s, elapsed: 2.34 s"),
        _record(3, "ERROR", "unrelated"),
    ]
    result = module.collect(_context(_window(records)))
    rows = _by(result)
    assert len(rows) == 2
    assert rows[0]["kind"] == "analyze"
    assert rows[0]["relation"] == "appdb.public.users"
    assert rows[0]["elapsed_s"] == 2.34
    assert rows[1]["kind"] == "vacuum"
    assert rows[1]["elapsed_s"] is None
    assert result.severity_level == "ok"


def test_checkpoints_parses_and_flags_forced() -> None:
    module = _load("checkpoints")
    records = [
        _record(1, "LOG", "checkpoint starting: wal"),
        _record(2, "LOG",
                "checkpoint complete: wrote 1234 buffers (7.5%); 1 WAL file(s) added; "
                "write=26.5 s, sync=0.1 s, total=26.7 s"),
    ]
    result = module.collect(_context(_window(records)))
    rows = _by(result)
    assert rows[0]["phase"] == "complete"
    assert rows[0]["buffers_written"] == 1234
    assert rows[0]["total_s"] == 26.7
    assert rows[1]["reason"] == "wal"
    assert result.severity_level == "medium"  # wal-forced checkpoint


def test_archiver_failures_high() -> None:
    module = _load("archiver_failures")
    records = [
        _record(1, "LOG", "archive command failed with exit code 1", repeat=25),
        _record(2, "ERROR", "unrelated"),
    ]
    result = module.collect(_context(_window(records)))
    rows = _by(result)
    assert len(rows) == 1
    assert rows[0]["repeat_count"] == 25
    assert result.severity_level == "high"
    assert result.issues["summary"]["status"] == "fail"


def test_wraparound_pressure_parses_database() -> None:
    module = _load("wraparound_pressure")
    records = [
        _record(1, "WARNING",
                'database "appdb" must be vacuumed within 5000000 transactions',
                sql_state="01000", repeat=3),
    ]
    result = module.collect(_context(_window(records)))
    rows = _by(result)
    assert rows[0]["database"] == "appdb"
    assert rows[0]["transactions_left"] == 5000000
    assert result.severity_level == "high"


def _inventory(files=None, **settings_overrides):
    settings = {
        "logging_collector": "on",
        "log_destination": "stderr,csvlog",
        "log_directory": "/var/log/postgresql",
        "log_filename": "postgresql-%Y.log",
        "log_rotation_age": "1d",
        "log_rotation_size": "10MB",
        "log_truncate_on_rotation": "off",
    }
    settings.update(settings_overrides)
    if files is None:
        files = [
            {"name": "a.csv", "size_bytes": 1000, "modification": "2026-08-31 10:00:00",
             "in_window": True, "is_current": True},
        ]
    return {
        "files": files,
        "file_count_total": len(files),
        "total_bytes": sum(f["size_bytes"] for f in files),
        "collected_to": "2026-08-31 10:00:00",
        "settings": settings,
    }


def _inventory_context(inventory, marker=None):
    if marker is None:
        marker = {"status": "collected", "reason": None, "coverage": {}}
    return SimpleNamespace(
        server_log=SimpleNamespace(window=None, marker=marker, inventory=inventory)
    )


def test_log_files_overview_ok_and_rotation_finding() -> None:
    module = _load("log_files_overview")
    result = module.collect(_inventory_context(_inventory()))
    assert result.collection_status == "ok"
    assert result.severity_level == "ok"

    result = module.collect(
        _inventory_context(_inventory(log_rotation_age="0", log_rotation_size="0"))
    )
    assert result.severity_level == "high"
    assert "rotation" in result.issues["summary"]["description"]


def test_log_files_overview_works_when_content_unavailable() -> None:
    module = _load("log_files_overview")
    marker = {"status": "unavailable", "reason": "no reader", "coverage": None}
    result = module.collect(_inventory_context(_inventory(), marker))
    assert result.collection_status == "ok"

    # but without inventory the item degrades to unsupported
    result = module.collect(_inventory_context(None, marker))
    assert result.collection_status == "unsupported"


def test_batch2_empty_statuses() -> None:
    for name in (
        "autovacuum_runs",
        "checkpoints",
        "archiver_failures",
        "wraparound_pressure",
        "lock_waits",
    ):
        module = _load(name)
        result = module.collect(_context(_window([])))
        assert result.collection_status == "empty", name


def test_lock_waits_parses_waiting_and_acquired() -> None:
    module = _load("lock_waits")
    records = [
        _record(
            1,
            "LOG",
            "process 4155 still waiting for AccessShareLock on relation 16423 of "
            "database 16401 after 1000.123 ms",
            detail="Process holding the lock: 4152. Wait queue: 4155, 4157, 4158.",
        ),
        _record(
            5,
            "LOG",
            "process 4155 acquired AccessShareLock on relation 16423 of database "
            "16401 after 4500.700 ms",
        ),
        _record(7, "ERROR", "unrelated error"),
    ]
    result = module.collect(_context(_window(records)))
    rows = _by(result)
    assert len(rows) == 2
    assert rows[0]["event"] == "acquired"
    assert rows[0]["wait_ms"] == 4500.7
    assert rows[1]["event"] == "waiting"
    assert rows[1]["relation_oid"] == 16423
    assert rows[1]["database_oid"] == 16401
    assert rows[1]["holder_pids"] == "4152"
    assert rows[1]["queue_depth"] == 3
    assert result.severity_level == "medium"


def test_lock_waits_high_on_access_exclusive() -> None:
    module = _load("lock_waits")
    records = [
        _record(
            1,
            "LOG",
            "process 900 still waiting for AccessExclusiveLock on relation 16423 of "
            "database 16401 after 12000.000 ms",
        ),
    ]
    result = module.collect(_context(_window(records)))
    assert result.severity_level == "high"
    assert result.issues["summary"]["status"] == "fail"


def test_lock_waits_tuple_and_transaction_targets() -> None:
    module = _load("lock_waits")
    records = [
        _record(
            1,
            "LOG",
            "process 1 still waiting for ShareLock on transaction 778 after 1001.0 ms",
        ),
        _record(
            2,
            "LOG",
            "process 2 still waiting for ExclusiveLock on tuple (0,10) of relation "
            "16423 of database 16401 after 1002.0 ms",
        ),
    ]
    rows = _by(module.collect(_context(_window(records))))
    kinds = {row["target_kind"] for row in rows}
    assert kinds == {"transaction", "tuple"}
    tuple_row = next(row for row in rows if row["target_kind"] == "tuple")
    assert tuple_row["relation_oid"] == 16423


def test_lock_waits_parses_detail_beyond_display_line_cap() -> None:
    module = _load("lock_waits")
    queue = list(range(5000, 5700))
    detail = (
        "Process holding the lock: 4152. Wait queue: " + ", ".join(str(pid) for pid in queue) + "."
    )
    record = _record(
        1,
        "LOG",
        "process 4155 still waiting for AccessShareLock on relation 16423 of "
        "database 16401 after 1000.123 ms",
        detail=detail,
    )

    row = _by(module.collect(_context(_window([record]))))[0]

    assert len(detail) > 2000
    assert row["holder_pids"] == "4152"
    assert row["queue_depth"] == len(queue)


def test_lock_waits_limit_does_not_hide_older_high_severity_event() -> None:
    module = _load("lock_waits")
    records = [
        _record(
            0,
            "LOG",
            "process 1 still waiting for AccessExclusiveLock on relation 1 of "
            "database 1 after 120000.0 ms",
        )
    ]
    records.extend(
        _record(
            offset,
            "LOG",
            f"process {offset + 1} still waiting for AccessShareLock on relation "
            f"{offset + 1} of database 1 after 1000.0 ms",
        )
        for offset in range(1, 201)
    )

    result = module.collect(_context(_window(records)))

    assert len(_by(result)) == 200
    assert result.severity_level == "high"
    assert "120000 ms" in result.issues["summary"]["description"]
    assert "newest 200" in result.issues["summary"]["description"]


def test_lock_waits_nonempty_result_discloses_incomplete_coverage() -> None:
    module = _load("lock_waits")
    record = _record(
        1,
        "LOG",
        "process 1 still waiting for AccessShareLock on relation 1 of database 1 "
        "after 1000.0 ms",
        count_complete=False,
    )

    result = module.collect(_context(_window([record], ranking_complete=False)))

    assert "Counts are lower bounds" in result.issues["summary"]["description"]
