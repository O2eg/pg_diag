"""Unit tests for server_log item sources against synthetic LogWindows."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from pg_diag.logscan.model import AutoExplainPlan, LogCoverage, LogRecord, LogWindow
from pg_diag.logscan.rle import fingerprint

CONTENT = Path("src/pg_diag/content/python/server_log")
BASE = datetime(2026, 8, 31, 10, 0, 0)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"server_log_{name}", CONTENT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
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
    auto_explain_plan: AutoExplainPlan | None = None,
    application_name: str | None = None,
    query: str | None = None,
    command_tag: str | None = None,
    message_full: str | None = None,
    context: str | None = None,
    backend_type: str | None = "client backend",
    query_id: int | None = 7,
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
        backend_type=backend_type,
        query_id=query_id,
        partial=False,
        count_complete=count_complete,
        encoding_degraded=False,
        fingerprint=fingerprint(message),
        detail=detail,
        auto_explain_plan=auto_explain_plan,
        application_name=application_name,
        query=query,
        command_tag=command_tag,
        message_full=message_full,
        context=context,
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


def _context(window=None, marker=None, *, mode=None, interval_seconds=None, inventory=None):
    if marker is None:
        marker = {"status": "collected", "reason": None, "coverage": {}}
    return SimpleNamespace(
        server_log=SimpleNamespace(
            window=window,
            marker=marker,
            mode=mode,
            interval_seconds=interval_seconds,
            inventory=inventory,
        )
    )


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


def test_message_dependent_items_reject_non_english_locale() -> None:
    for name in (
        "error_chronology",
        "top_errors",
        "top_warnings",
        "crash_recovery_events",
        "autovacuum_runs",
        "checkpoints",
        "archiver_failures",
        "wraparound_pressure",
        "lock_waits",
        "auto_explain_plans",
        "server_lifecycle",
        "replication_events",
        "query_resource_events",
        "maintenance_events",
    ):
        module = _load(name)
        result = module.collect(_context(_window([], locale_supported=False)))
        assert result.collection_status == "unsupported", name
        assert "lc_messages" in result.reason, name


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


def test_deadlock_events_support_non_english_locale_via_sqlstate() -> None:
    module = _load("deadlock_events")
    record = _record(
        1,
        "ОШИБКА",
        "обнаружена взаимоблокировка",
        sql_state="40P01",
    )
    result = module.collect(_context(_window([record], locale_supported=False)))
    assert result.collection_status == "ok"
    assert result.result["row_count"] == 1
    assert result.severity_level == "medium"


def test_authentication_failures_grouping() -> None:
    module = _load("authentication_failures")
    records = [
        _record(
            1,
            "FATAL",
            'password authentication failed for user "svc"',
            sql_state="28P01",
            user="svc",
            repeat=10,
            connection_from="10.0.0.1:50001",
        ),
        _record(
            90,
            "FATAL",
            'password authentication failed for user "svc"',
            sql_state="28P01",
            user="svc",
            repeat=5,
            connection_from="10.0.0.1:50777",
        ),
        _record(
            3,
            "FATAL",
            "no pg_hba.conf entry for host",
            sql_state="28000",
            user="other",
            connection_from="10.9.9.9:1",
        ),
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


def test_authentication_failures_support_non_english_locale_via_sqlstate() -> None:
    module = _load("authentication_failures")
    record = _record(
        1,
        "ОШИБКА",
        "проверка пароля не пройдена",
        sql_state="28P01",
        user="svc",
    )
    result = module.collect(_context(_window([record], locale_supported=False)))
    assert result.collection_status == "ok"
    assert result.result["row_count"] == 1
    assert result.severity_level == "medium"


def test_sqlstate_items_can_prove_empty_in_non_english_locale() -> None:
    for name in ("deadlock_events", "authentication_failures"):
        module = _load(name)
        result = module.collect(_context(_window([], locale_supported=False)))
        assert result.collection_status == "empty", name
        assert result.severity_level == "ok", name


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


def test_auto_explain_chart_keeps_top_ten_queries_per_minute() -> None:
    module = _load("auto_explain_plans")

    def plan(
        duration_ms: float,
        query_sample: str,
        plan_format: str = "json",
    ) -> AutoExplainPlan:
        if plan_format == "json":
            viewer_body = '{"Query Text":"' + query_sample + '","Plan":{"Node Type":"Result"}}'
        else:
            viewer_body = f"Query Text: {query_sample}\nResult  (cost=0.00..0.01 rows=1 width=4)"
        return AutoExplainPlan(
            duration_ms,
            plan_format,
            "Result",
            1,
            True,
            True,
            query_sample,
            f"duration: {duration_ms} ms  plan:\n{viewer_body}",
        )

    records = [
        _record(
            offset,
            "LOG",
            auto_explain_plan=plan(offset * 100.0, f"select {offset}"),
        )
        for offset in range(1, 13)
    ]
    records.extend(
        [
            _record(61, "LOG", auto_explain_plan=plan(5_000, "select slow")),
            _record(62, "LOG", auto_explain_plan=plan(2_000, "select less_slow", "text")),
        ]
    )
    inventory = {
        "window_from": "2026-08-31 10:00:00",
        "collected_to": "2026-08-31 10:01:20",
        "settings": {"log_utc_offset_seconds": 0},
    }
    result = module.collect(
        _context(
            _window(records),
            mode="snapshots",
            interval_seconds=5,
            inventory=inventory,
        )
    )
    assert result.collection_status == "ok"
    assert result.result["chart"]["kind"] == "stacked_column"
    assert result.result["chart"]["quantity"] == "milliseconds"
    assert result.result["chart"]["unit"] == "milliseconds"
    assert result.result["bucket_seconds"] == 60
    assert result.result["top_queries_per_bucket"] == 10
    assert result.result["plan_count"] == 14
    assert result.result["displayed_plan_count"] == 12
    assert result.result["omitted_plan_count"] == 2
    assert result.result["parsed_plan_count"] == 14
    assert result.result["plan_format_counts"] == {"json": 13, "text": 1}
    assert result.result["chart"]["show_legend"] is False
    assert result.result["chart"]["tooltip_kind"] == "query_event"
    assert len(result.result["series"]) == 10
    assert [series["name"] for series in result.result["series"]] == [
        f"Rank {rank}" for rank in range(10, 0, -1)
    ]
    slowest = [point for point in result.result["series"][-1]["points"] if point["value"]]
    second = [point for point in result.result["series"][-2]["points"] if point["value"]]
    assert [point["value"] for point in slowest] == [1_200, 5_000]
    assert [point["tooltip"]["duration_ms"] for point in slowest] == [1_200, 5_000]
    query_refs = result.result["references"]["queries"]
    assert [query_refs[point["tooltip"]["query_ref"]] for point in slowest] == [
        "select 12",
        "select slow",
    ]
    assert [point["tooltip"]["duration_ms"] for point in second] == [1_100, 2_000]
    first_minute_values = [
        next(point for point in series["points"] if point["value"])["value"]
        for series in result.result["series"]
    ]
    first_minute_colors = [
        next(point for point in series["points"] if point["value"])["color"]
        for series in result.result["series"]
    ]
    assert first_minute_values == list(range(300, 1_300, 100))
    assert first_minute_colors[0] == "#facc15"
    assert first_minute_colors[-1] == "#ef4444"
    assert len(set(first_minute_colors)) == 10
    second_minute_points = [
        point
        for series in result.result["series"]
        for point in series["points"]
        if point["value"] and point["t"].startswith("2026-08-31T10:01")
    ]
    assert [point["value"] for point in second_minute_points] == [2_000, 5_000]
    assert [point["color"] for point in second_minute_points] == ["#facc15", "#ef4444"]
    viewer = slowest[0]["viewer"]
    assert viewer == {"plan_ref": viewer["plan_ref"], "read_only": True}
    assert result.result["references"]["plans"][viewer["plan_ref"]] == {
        "format": "json",
        "text": (
            "duration: 1200.0 ms  plan:\n"
            '{"Query Text":"select 12","Plan":{"Node Type":"Result"}}'
        ),
    }


def test_auto_explain_chart_always_uses_aligned_minute_buckets() -> None:
    module = _load("auto_explain_plans")
    plan = AutoExplainPlan(10_000, "yaml", "Result", 1, True, True, "select 1")
    record = _record(301, "LOG", auto_explain_plan=plan)
    inventory = {
        "window_from": "2026-08-31 09:58:00",
        "collected_to": "2026-08-31 10:07:00",
        "settings": {"log_utc_offset_seconds": 10_800},
    }
    result = module.collect(_context(_window([record]), mode="one-shot", inventory=inventory))
    assert result.result["bucket_seconds"] == 60
    series = result.result["series"][-1]
    assert series["points"][0]["t"] == "2026-08-31T09:58:00+03:00"
    assert series["points"][-1]["t"] == "2026-08-31T10:07:00+03:00"
    assert [point["value"] for point in series["points"]] == [0, 10_000, 0]
    assert series["points"][1]["color"] == "#ef4444"
    assert series["points"][1]["tooltip"] == {
        "log_time": "2026-08-31T10:05:01+03:00",
        "duration_ms": 10_000,
        "query_ref": "q1",
    }


def _by(result):
    res = result.result
    cols = [c["name"] if isinstance(c, dict) else c for c in res["columns"]]
    rows = res["rows"]
    return [dict(zip(cols, r)) for r in rows] if rows and isinstance(rows[0], list) else rows


def test_autovacuum_runs_parses_relation_and_elapsed() -> None:
    module = _load("autovacuum_runs")
    records = [
        _record(1, "LOG", 'automatic vacuum of table "appdb.public.orders": index scans: 1'),
        _record(
            2,
            "LOG",
            'automatic analyze of table "appdb.public.users" system usage: '
            "CPU: user: 0.01 s, system: 0.00 s, elapsed: 2.34 s",
        ),
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
        _record(
            2,
            "LOG",
            "checkpoint complete: wrote 1234 buffers (7.5%); 1 WAL file(s) added; "
            "write=26.5 s, sync=0.1 s, total=26.7 s",
        ),
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
        _record(
            1,
            "WARNING",
            'database "appdb" must be vacuumed within 5000000 transactions',
            sql_state="01000",
            repeat=3,
        ),
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
            {
                "name": "a.csv",
                "size_bytes": 1000,
                "modification": "2026-08-31 10:00:00",
                "in_window": True,
                "is_current": True,
            },
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


def test_system_incidents_uses_sqlstate_across_locales_and_reports_partial_patterns() -> None:
    module = _load("system_incidents")
    records = [
        _record(1, "ОШИБКА", "на устройстве нет места", sql_state="53100", repeat=3),
        _record(2, "PANIC", "invalid record length at 1/2", sql_state="XX001"),
    ]
    result = module.collect(_context(_window(records, locale_supported=False)))
    rows = _by(result)
    assert {row["incident_type"] for row in rows} == {"disk_full", "data_corruption"}
    assert result.result["message_pattern_coverage"] == "structured_sqlstate_only"
    assert result.severity_level == "unknown"
    assert "SQLSTATE incidents are included" in result.issues["summary"]["description"]


def test_server_lifecycle_and_replication_classify_key_events() -> None:
    lifecycle = _load("server_lifecycle")
    lifecycle_result = lifecycle.collect(
        _context(
            _window(
                [
                    _record(1, "LOG", "database system was not properly shut down", None),
                    _record(2, "LOG", "database system is ready to accept connections", None),
                ]
            )
        )
    )
    assert {row["event_type"] for row in _by(lifecycle_result)} == {
        "unclean_shutdown",
        "ready",
    }
    assert lifecycle_result.severity_level == "high"

    replication = _load("replication_events")
    replication_result = replication.collect(
        _context(
            _window(
                [
                    _record(1, "LOG", "archive command failed with exit code 1", None),
                    _record(2, "ERROR", "requested WAL segment 00000001 has already been removed"),
                    _record(3, "LOG", "could not receive data from client: Connection reset"),
                ]
            )
        )
    )
    assert {row["event_type"] for row in _by(replication_result)} == {
        "archive_failure",
        "wal_missing",
        "walsender_disconnect",
    }

    normal_replication = replication.collect(
        _context(
            _window(
                [
                    _record(4, "LOG", 'created replication slot "healthy_slot"'),
                    _record(5, "LOG", "logical replication apply worker started"),
                    _record(6, "ERROR", 'cannot use replication slot "broken_slot"'),
                ]
            )
        )
    )
    assert [row["event_type"] for row in _by(normal_replication)] == ["replication_slot"]


def test_query_termination_chart_deduplicates_references_and_keeps_minutes() -> None:
    module = _load("query_termination_events")
    message = "canceling statement due to statement timeout"
    records = [
        _record(
            5,
            "ERROR",
            message,
            "57014",
            application_name="api",
            query="select * from orders where id = 1",
        ),
        _record(
            65,
            "ERROR",
            message,
            "57014",
            application_name="api",
            query="select * from orders where id = 1",
        ),
        _record(70, "ERROR", "could not obtain lock on row", "55P03", query="select 2"),
    ]
    result = module.collect(
        _context(_window(records), inventory={"settings": {"log_utc_offset_seconds": 0}})
    )
    assert result.result["chart"]["tooltip_kind"] == "log_event"
    assert result.result["displayed_point_count"] == 3
    assert result.result["references"]["messages"] == {
        "m1": message,
        "m2": "could not obtain lock on row",
    }
    assert result.result["references"]["queries"]["q1"] == ("select * from orders where id = 1")
    points = [point for series in result.result["series"] for point in series["points"]]
    assert {point["t"] for point in points} == {
        "2026-08-31T10:00:00+00:00",
        "2026-08-31T10:01:00+00:00",
    }
    timeout_points = [
        point for point in points if point["tooltip"]["event_type"] == "statement_timeout"
    ]
    assert {point["tooltip"]["message_ref"] for point in timeout_points} == {"m1"}
    assert {point["tooltip"]["query_ref"] for point in timeout_points} == {"q1"}


def test_query_resource_events_aggregate_slow_queries_and_temp_files() -> None:
    module = _load("query_resource_events")
    records = [
        _record(
            1,
            "LOG",
            "duration: 120.5 ms  statement: select * from orders",
            "00000",
            repeat=2,
            query="select * from orders",
            application_name="api",
        ),
        _record(
            2,
            "LOG",
            'temporary file: path "base/pgsql_tmp/x", size 67108864',
            "00000",
            query="select * from orders order by created_at",
            application_name="api",
        ),
    ]
    result = module.collect(_context(_window(records)))
    rows = _by(result)
    assert result.result["raw_event_count"] == 3
    assert {row["event_type"] for row in rows} == {"slow_statement", "temporary_file"}
    slow = next(row for row in rows if row["event_type"] == "slow_statement")
    assert slow["max_duration_ms"] == 120.5
    assert slow["total_duration_ms"] == 241.0
    temporary = next(row for row in rows if row["event_type"] == "temporary_file")
    assert temporary["total_temp_bytes"] == 67_108_864


def test_maintenance_events_apply_thresholds_and_always_keep_failures() -> None:
    module = _load("maintenance_events")
    light = (
        'automatic vacuum of table "appdb.public.light": pages: 0 removed, 10 remain, '
        "10 scanned; tuples: 10 removed; buffer usage: 2 hits, 3 misses, 1 dirtied; "
        "WAL usage: 2 records, 0 full page images, 100 bytes; elapsed: 0.1 s"
    )
    heavy = (
        'automatic vacuum of table "appdb.public.heavy": pages: 0 removed, 20000 remain, '
        "20000 scanned; tuples: 150000 removed; buffer usage: 1 hits, 20000 misses, "
        "1 dirtied; WAL usage: 2 records, 0 full page images, 70000000 bytes; "
        "elapsed: 7.5 s"
    )
    failed = _record(
        3,
        "ERROR",
        "canceling autovacuum task",
        "57014",
        command_tag="VACUUM",
    )
    result = module.collect(
        _context(
            _window(
                [
                    _record(1, "LOG", light, "00000", message_full=light),
                    _record(2, "LOG", heavy, "00000", message_full=heavy),
                    failed,
                ]
            ),
            inventory={"settings": {"block_size": 8192}},
        )
    )
    rows = _by(result)
    assert len(rows) == 2
    assert result.result["below_threshold_event_count"] == 1
    assert result.result["thresholds"]["duration_seconds"] == 5.0
    assert rows[0]["inclusion_reason"] in {"threshold_exceeded", "error_or_cancellation"}
    heavy_row = next(row for row in rows if row["relation"] == "appdb.public.heavy")
    assert heavy_row["processed_bytes"] == 20_000 * 8192
    assert heavy_row["processed_pages"] == 20_000
    assert heavy_row["tuples_removed"] == 150_000
    assert heavy_row["wal_bytes"] == 70_000_000
    assert any(row["inclusion_reason"] == "error_or_cancellation" for row in rows)
    assert result.severity_level == "high"


def test_maintenance_events_parse_legacy_autovacuum_pages_without_scanned() -> None:
    module = _load("maintenance_events")
    message = (
        'automatic vacuum of table "app_01.pg_catalog.pg_statistic": index scans: 1\n'
        "pages: 0 removed, 20000 remain, 0 skipped due to pins, 0 skipped frozen\n"
        "tuples: 114 removed, 509 remain, 0 are dead but not yet removable\n"
        "buffer usage: 105 hits, 4 misses, 0 dirtied\n"
        "system usage: CPU: user: 0.00 s, system: 0.00 s, elapsed: 6.00 s"
    )
    result = module.collect(
        _context(
            _window([_record(1, "LOG", message, "00000", message_full=message)]),
            inventory={"settings": {"block_size": 8192}},
        )
    )
    row = _by(result)[0]
    assert row["scanned_pages"] is None
    assert row["processed_pages"] is None
    assert row["processed_bytes"] is None
    assert row["pages_removed"] == 0
    assert row["relation_pages_after"] == 20_000
    assert row["inclusion_reason"] == "threshold_exceeded"


def test_maintenance_events_always_keeps_logged_lock_waits() -> None:
    module = _load("maintenance_events")
    message = "process 901 still waiting for ShareLock on transaction 778 " "after 1250.5 ms"
    result = module.collect(
        _context(
            _window(
                [
                    _record(
                        1,
                        "LOG",
                        message,
                        "00000",
                        command_tag="VACUUM",
                    )
                ]
            )
        )
    )

    row = _by(result)[0]
    assert row["kind"] == "vacuum"
    assert row["inclusion_reason"] == "lock_wait"
    assert row["duration_s"] == 1.2505
    assert result.severity_level == "high"


def test_maintenance_keeps_native_autovacuum_cancellation_context() -> None:
    module = _load("maintenance_events")
    for backend in ("autovacuum worker", None):  # CSV before PG13 has no backend_type.
        record = _record(
            1,
            "ERROR",
            "canceling autovacuum task",
            "57014",
            backend_type=backend,
            command_tag=None,
            context='automatic vacuum of table "appdb.public.accounts"',
        )
        result = module.collect(_context(_window([record])))
        row = _by(result)[0]
        assert row["kind"] == "autovacuum"
        assert row["relation"] == "appdb.public.accounts"
        assert row["inclusion_reason"] == "error_or_cancellation"
        assert row["duration_s"] is None
        assert result.severity_level == "high"

    # Autoanalyze uses the same cancellation message but a different context.
    analyzed = replace(record, context='automatic analyze of table "appdb.public.accounts"')
    result = module.collect(_context(_window([analyzed])))
    assert _by(result)[0]["kind"] == "autoanalyze"
    # A missing/truncated context must not suppress the cancellation itself.
    result = module.collect(_context(_window([replace(record, context=None)])))
    assert _by(result)[0]["relation"] is None
    assert result.severity_level == "high"


def test_termination_burst_aggregates_repeats_before_ranking() -> None:
    module = _load("query_termination_events")
    records = [
        _record(
            i,
            "ERROR",
            "canceling statement due to statement timeout",
            "57014",
            query="SELECT pg_sleep(1)",
            application_name="api",
        )
        for i in range(15)
    ]
    result = module.collect(_context(_window(records)))
    data = result.result
    points = [point for series in data["series"] for point in series["points"]]
    assert len(points) == 1
    assert points[0]["value"] == 15
    assert points[0]["tooltip"]["log_time"] == "2026-08-31T10:00:00+00:00"
    assert points[0]["tooltip"]["last_log_time"] == "2026-08-31T10:00:14+00:00"
    assert data["event_count"] == data["displayed_event_count"] == 15
    assert data["omitted_event_count"] == data["omitted_point_count"] == 0


def test_termination_reports_per_minute_and_global_omissions(monkeypatch) -> None:
    module = _load("query_termination_events")
    records = [
        _record(
            i,
            "ERROR",
            "canceling statement due to statement timeout",
            "57014",
            query=f"SELECT pg_sleep({i})",
            application_name="api",
        )
        for i in range(15)
    ]
    result = module.collect(_context(_window(records)))
    data = result.result
    assert data["candidate_point_count"] == data["event_count"] == 15
    assert data["displayed_point_count"] == data["displayed_event_count"] == 10
    assert data["omitted_point_count"] == data["omitted_event_count"] == 5
    assert result.severity_level == "unknown"
    assert "5 groups containing 5 events" in result.issues["summary"]["description"]

    monkeypatch.setattr(module, "CHART_POINT_LIMIT", 3)
    records = [
        replace(
            record,
            log_time=BASE + timedelta(minutes=i),
            last_time=BASE + timedelta(minutes=i),
            repeat_count=2,
        )
        for i, record in enumerate(records[:4])
    ]
    result = module.collect(_context(_window(records)))
    assert result.result["displayed_point_count"] == 3
    assert result.result["omitted_point_count"] == 1
    assert result.result["displayed_event_count"] == 6
    assert result.result["omitted_event_count"] == 2
    assert result.severity_level == "unknown"


def test_termination_keeps_different_query_and_application_groups() -> None:
    module = _load("query_termination_events")
    first = _record(
        1,
        "ERROR",
        "canceling statement due to statement timeout",
        "57014",
        query="SELECT 1",
        application_name="api",
    )
    records = [
        first,
        replace(first, query="SELECT 2"),
        replace(first, application_name="batch"),
        replace(first, user_name="bob"),
    ]
    result = module.collect(_context(_window(records)))
    assert result.result["candidate_point_count"] == 4


def test_resource_ignores_plans_parse_bind_and_bare_duration_records() -> None:
    module = _load("query_resource_events")
    messages = [
        "duration: 20.161 ms  statement: SELECT pg_sleep(0.02)",
        "duration: 201.236 ms  execute <unnamed>: SELECT pg_sleep(0.2)",
        'duration: 20.0 ms  plan:\n{"Plan":{"Node Type":"Result"}}',
        "duration: 10.0 ms  parse <unnamed>: SELECT 1",
        "duration: 10.0 ms  bind <unnamed>: SELECT 1",
        "duration: 10.0 ms",
    ]
    records = [_record(i, "LOG", message, "00000") for i, message in enumerate(messages)]
    standalone = module.collect(_context(_window(records[:2])))
    combined = module.collect(_context(_window(records)))
    assert combined.result == standalone.result
    row = _by(combined)[0]
    assert row["occurrences"] == 2
    assert row["max_duration_ms"] == 201.236
    assert row["total_duration_ms"] == 221.397


def test_resource_zero_query_id_uses_sql_identity() -> None:
    module = _load("query_resource_events")
    for query_id in (0, None):
        records = [
            _record(
                i, "LOG", f"duration: {duration} ms  statement: {query}", "00000", query_id=query_id
            )
            for i, (duration, query) in enumerate(
                [
                    (30, "SELECT pg_sleep(0.03)"),
                    (40, "SELECT md5('beta')"),
                    (50, "SELECT pg_sleep(0.03)"),
                ]
            )
        ]
        result = module.collect(_context(_window(records)))
        rows = {row["query_sample"]: row for row in _by(result)}
        assert len(rows) == 2
        assert rows["SELECT pg_sleep(0.03)"]["occurrences"] == 2
        assert rows["SELECT pg_sleep(0.03)"]["total_duration_ms"] == 80
        assert rows["SELECT md5('beta')"]["total_duration_ms"] == 40
        assert all(row["query_id"] is None for row in rows.values())


def test_normal_end_of_wal_is_lifecycle_evidence_not_corruption() -> None:
    incidents = _load("system_incidents")
    lifecycle = _load("server_lifecycle")
    message = "invalid record length at 0/5E15058: expected at least 24, got 0"
    for backend in ("startup", None):
        record = _record(1, "LOG", message, "00000", backend_type=backend)
        result = incidents.collect(_context(_window([record])))
        assert result.collection_status == "empty"
        assert result.severity_level == "ok"
        result = lifecycle.collect(_context(_window([record])))
        assert _by(result)[0]["event_type"] == "recovery_wal_end"
        assert result.severity_level == "ok"

    # Keep explicit errors, nonzero lengths and messages outside startup.
    for record in (
        _record(1, "PANIC", message, "XX001", backend_type="startup"),
        _record(1, "LOG", message.replace("got 0", "got 12"), "00000", backend_type="startup"),
        _record(1, "ERROR", message, "00000", backend_type="startup"),
        _record(1, "LOG", message, "00000", backend_type="client backend"),
    ):
        result = incidents.collect(_context(_window([record])))
        assert len(_by(result)) == 1


def test_system_incidents_do_not_classify_application_identifiers_as_incidents() -> None:
    module = _load("system_incidents")
    records = [
        _record(1, message='relation "out of memory" does not exist', sql_state="42P01"),
        _record(2, message='column "could not write" does not exist', sql_state=None),
        _record(3, message="out of memory", sql_state="42P01"),
        _record(4, message="out of memory", sql_state=None),
        _record(5, message="не хватает памяти", sql_state="53200"),
        _record(6, message='could not fsync file "base/1/2": Input/output error', sql_state=None),
        _record(7, message='could not write to file "pg_wal/xlogtemp.12": No space left on device',
                sql_state=None),
    ]
    rows = _by(module.collect(_context(_window(records))))
    assert len(rows) == 4
    assert sorted(row["incident_type"] for row in rows) == [
        "disk_full", "fsync_failure", "out_of_memory", "out_of_memory",
    ]


def test_checkpoint_item_preserves_cap_and_rle_coverage() -> None:
    module = _load("checkpoints")
    records = [
        _record(n, "LOG", "checkpoint starting: time", sql_state=None)
        for n in range(module.EVENT_LIMIT + 1)
    ]
    records[-1] = _record(module.EVENT_LIMIT, "LOG", "checkpoint starting: wal", repeat=3,
                          sql_state=None, count_complete=False)
    result = module.collect(_context(_window(records)))
    assert result.result["matched_series_count"] == module.EVENT_LIMIT + 1
    assert result.result["omitted_series_count"] == 1
    assert result.result["row_limit"] == module.EVENT_LIMIT
    latest = _by(result)[0]
    assert latest["repeat_count"] == 3
    assert latest["count_complete"] is False
    assert latest["last_time"] > latest["log_time"]
    assert "3 checkpoint(s)" in result.issues["summary"]["description"]
    empty = module.collect(_context(_window([])))
    assert empty.result["omitted_series_count"] == 0


def test_explicit_checkpoints_and_sql_fragments_are_not_wal_pressure() -> None:
    module = _load("checkpoints")
    records = [
        _record(1, "LOG", "checkpoint starting: immediate force wait", sql_state=None),
        _record(2, message='relation "checkpoint starting: wal" does not exist'),
    ]
    result = module.collect(_context(_window(records)))
    assert len(_by(result)) == 1
    assert result.severity_level == "ok"
    assert result.result["omitted_series_count"] == 0


def test_checkpoint_item_carries_server_timezone_offset() -> None:
    module = _load("checkpoints")
    window = _window([_record(1, "LOG", "checkpoint starting: time", sql_state=None)])
    result = module.collect(_context(window, inventory={"settings": {"log_utc_offset_seconds": 10800}}))
    assert result.result["log_utc_offset_seconds"] == 10800
    legacy = module.collect(_context(window))
    assert legacy.result["log_utc_offset_seconds"] is None
