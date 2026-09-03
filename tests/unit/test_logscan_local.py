"""End-to-end tests for LocalLogSource against synthetic csvlog files."""

from __future__ import annotations

import asyncio
import csv
from datetime import datetime, timedelta
import io

from pg_diag.logscan.model import LogFileInfo, ScanRequest
from pg_diag.logscan.recall import compile_clauses
from pg_diag.logscan.sources import LocalLogSource

BASE = datetime(2026, 8, 31, 10, 0, 0)
RECALL = compile_clauses([[",ERROR,"], [",WARNING,"]])


def _record(ts: datetime, severity: str = "LOG", message: str = "noise") -> str:
    stamp = ts.strftime("%Y-%m-%d %H:%M:%S.000 UTC")
    return (
        f"{stamp},alice,appdb,42,c,s,7,SELECT,start,3/44,778,"
        f"{severity},00000,{message},,,,,,,,loc,app,client backend,,1\n"
    )


def _write(tmp_path, name: str, body: str) -> LogFileInfo:
    path = tmp_path / name
    path.write_text(body)
    return LogFileInfo(name=name, size=path.stat().st_size, modification=BASE)


def _multiline_record(ts: datetime, message: str) -> str:
    fields = [
        ts.strftime("%Y-%m-%d %H:%M:%S.000 UTC"),
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
        "LOG",
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
        "1",
    ]
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerow(fields)
    return output.getvalue()


def _request(
    tmp_path, files, window_from: datetime, window_to: datetime | None = None, **kwargs
) -> ScanRequest:
    if window_to is None:
        window_to = window_from + timedelta(hours=1)
    recall_clauses = kwargs.pop("recall_clauses", RECALL)
    return ScanRequest(
        log_directory=str(tmp_path),
        files=tuple(files),
        window_from_ts=window_from.strftime("%Y-%m-%d %H:%M:%S"),
        window_to_ts=window_to.strftime("%Y-%m-%d %H:%M:%S"),
        recall_clauses=recall_clauses,
        **kwargs,
    )


def test_local_scan_filters_and_collapses_flood(tmp_path) -> None:
    body = _record(BASE + timedelta(seconds=1), "ERROR", "unique one")
    body += "".join(
        _record(BASE + timedelta(seconds=2), "ERROR", "syntax error near X") for _ in range(1000)
    )
    body += _record(BASE + timedelta(seconds=3), "LOG", "in between noise")
    body += _record(BASE + timedelta(seconds=4), "ERROR", "unique two")
    info = _write(tmp_path, "a.csv", body)
    result = asyncio.run(LocalLogSource(str(tmp_path)).scan(_request(tmp_path, [info], BASE)))
    counts = [series.count for series in result.series]
    assert counts == [1, 1000, 1]
    assert result.stats.matched_lines == 1002
    assert result.stats.files_read == 1


def test_local_scan_reassembles_multiline_csv_records(tmp_path) -> None:
    message = (
        'duration: 12.5 ms  plan:\n{"Query Text":"select 1","Plan":{\n' '  "Node Type":"Result"\n}}'
    )
    body = _multiline_record(BASE + timedelta(seconds=1), message)
    body += _multiline_record(BASE + timedelta(seconds=2), message)
    info = _write(tmp_path, "a.csv", body)
    recall = compile_clauses([[",LOG,00000,", "duration: ", " ms  plan:"]])
    result = asyncio.run(
        LocalLogSource(str(tmp_path)).scan(_request(tmp_path, [info], BASE, recall_clauses=recall))
    )
    assert len(result.series) == 2
    assert all(series.count == 1 for series in result.series)
    assert all(series.last_lineno > series.first_lineno for series in result.series)
    assert b'""Node Type"":""Result""' in result.series[0].raw_record
    assert result.stats.matched_lines == 2


def test_local_scan_caps_complete_multiline_record_honestly(tmp_path) -> None:
    message = "duration: 12.5 ms  plan:\n" + ("x" * 500)
    info = _write(tmp_path, "a.csv", _multiline_record(BASE + timedelta(seconds=1), message))
    recall = compile_clauses([[",LOG,00000,", "duration: ", " ms  plan:"]])
    result = asyncio.run(
        LocalLogSource(str(tmp_path)).scan(
            _request(tmp_path, [info], BASE, recall_clauses=recall, raw_record_cap=128)
        )
    )
    assert len(result.series) == 1
    assert result.series[0].raw_truncated
    assert len(result.series[0].raw_record) == 128


def test_local_scan_window_binary_search(tmp_path) -> None:
    old = "".join(
        _record(BASE - timedelta(minutes=60) + timedelta(seconds=i), "ERROR", "old")
        for i in range(200)
    )
    fresh = "".join(_record(BASE + timedelta(seconds=i), "ERROR", "fresh") for i in range(5))
    info = _write(tmp_path, "a.csv", old + fresh)
    result = asyncio.run(LocalLogSource(str(tmp_path)).scan(_request(tmp_path, [info], BASE)))
    # binary search may include a small overlap; the fresh run must be present
    assert any(b"fresh" in series.raw_record for series in result.series)
    assert result.stats.scanned_bytes < info.size


def test_local_scan_vanished_file(tmp_path) -> None:
    info = LogFileInfo(name="gone.csv", size=100, modification=BASE)
    result = asyncio.run(LocalLogSource(str(tmp_path)).scan(_request(tmp_path, [info], BASE)))
    assert result.stats.files_vanished == 1
    assert "rotation_race" in result.stats.truncation_reasons
    assert result.series == []


def test_local_scan_unterminated_tail_dropped(tmp_path) -> None:
    body = _record(BASE + timedelta(seconds=1), "ERROR", "complete")
    body += _record(BASE + timedelta(seconds=2), "ERROR", "cutoff").rstrip("\n")
    info = _write(tmp_path, "a.csv", body)
    result = asyncio.run(LocalLogSource(str(tmp_path)).scan(_request(tmp_path, [info], BASE)))
    assert len(result.series) == 1
    assert b"complete" in result.series[0].raw_record
    assert result.stats.dropped_lines == 1


def test_local_scan_wire_budget_truncates(tmp_path) -> None:
    body = "".join(
        _record(BASE + timedelta(seconds=i), "ERROR", f"distinct {chr(65 + i % 26)} {i}")
        for i in range(300)
    )
    info = _write(tmp_path, "a.csv", body)
    result = asyncio.run(
        LocalLogSource(str(tmp_path)).scan(_request(tmp_path, [info], BASE, wire_budget_bytes=4096))
    )
    assert "return_limit_hit" in result.stats.truncation_reasons
    assert result.series  # something retained before the cut


def test_local_scan_scan_budget_tail_biased(tmp_path) -> None:
    body = "".join(
        _record(BASE + timedelta(seconds=i), "ERROR", f"seq {i:06d}") for i in range(2000)
    )
    info = _write(tmp_path, "a.csv", body)
    result = asyncio.run(
        LocalLogSource(str(tmp_path)).scan(
            _request(tmp_path, [info], BASE, scan_budget_bytes=64 * 1024)
        )
    )
    assert "scan_limit_hit" in result.stats.truncation_reasons
    # tail-biased: the newest record must survive
    assert any(b"seq 001999" in series.raw_record for series in result.series)
    assert not any(b"seq 000000" in series.raw_record for series in result.series)


def test_local_scan_upper_bound_excludes_future_lines(tmp_path) -> None:
    body = _record(BASE + timedelta(seconds=1), "ERROR", "inside window")
    body += _record(BASE + timedelta(minutes=90), "ERROR", "after window_to")
    info = _write(tmp_path, "a.csv", body)
    result = asyncio.run(
        LocalLogSource(str(tmp_path)).scan(
            _request(tmp_path, [info], BASE, window_to=BASE + timedelta(minutes=30))
        )
    )
    assert len(result.series) == 1
    assert b"inside window" in result.series[0].raw_record


def test_local_scan_series_split_at_lower_boundary(tmp_path) -> None:
    # 100 identical records straddling the boundary: only in-window ones count
    body = "".join(
        _record(BASE - timedelta(seconds=50) + timedelta(seconds=i), "ERROR", "straddle")
        for i in range(100)
    )
    info = _write(tmp_path, "a.csv", body)
    result = asyncio.run(LocalLogSource(str(tmp_path)).scan(_request(tmp_path, [info], BASE)))
    total = sum(series.count for series in result.series)
    assert total == 50  # records before window_from are excluded, not annexed


def test_local_scan_wire_budget_is_hard(tmp_path) -> None:
    body = _record(BASE + timedelta(seconds=1), "ERROR", "x" * 100)
    info = _write(tmp_path, "a.csv", body)
    result = asyncio.run(
        LocalLogSource(str(tmp_path)).scan(_request(tmp_path, [info], BASE, wire_budget_bytes=1))
    )
    assert result.series == []
    assert "return_limit_hit" in result.stats.truncation_reasons


def test_local_scan_refuses_symlink_escape(tmp_path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.csv"
    secret.write_text(_record(BASE + timedelta(seconds=1), "ERROR", "leaked"))
    logdir = tmp_path / "log"
    logdir.mkdir()
    (logdir / "evil.csv").symlink_to(secret)
    info = LogFileInfo(name="evil.csv", size=100, modification=BASE)
    result = asyncio.run(LocalLogSource(str(logdir)).scan(_request(logdir, [info], BASE)))
    assert result.series == []
    assert result.stats.files_unreadable == 1
    assert "files_unreadable" in result.stats.truncation_reasons


def test_local_scan_cooperative_deadline(tmp_path) -> None:
    info = _write(tmp_path, "a.csv", _record(BASE + timedelta(seconds=1), "ERROR", "x"))
    result = asyncio.run(
        LocalLogSource(str(tmp_path)).scan(
            _request(tmp_path, [info], BASE, deadline_monotonic=0.0)  # already expired
        )
    )
    assert result.stats.files_read == 0
    assert "time_limit_hit" in result.stats.truncation_reasons
