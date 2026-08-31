"""Harvester tests: the generated POSIX-sh script runs under a real local sh."""

from __future__ import annotations

import asyncio
import subprocess
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from pg_diag.logscan.harvester import (
    BashHarvesterSource,
    HarvesterProtocolError,
    HarvesterUnavailableError,
    build_script,
    parse_output,
)
from pg_diag.logscan.model import LogFileInfo, ScanRequest, ScanStats
from pg_diag.logscan.recall import compile_clauses
from pg_diag.logscan.sources import LocalLogSource

BASE = datetime(2026, 8, 31, 10, 0, 0)
RECALL = compile_clauses([[",ERROR,"], [",WARNING,"]])


class LocalShellTransport:
    """Executes the harvester through the local /bin/sh (test double)."""

    async def run_script_bytes(self, script: bytes, *, arguments=(), timeout: float):
        proc = subprocess.run(
            ["/bin/sh", "-s", "--", *arguments],
            input=script,
            capture_output=True,
            timeout=timeout,
        )
        return SimpleNamespace(
            returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
        )


def _record(ts: datetime, severity: str = "LOG", message: str = "noise",
            user: str = "alice", db: str = "appdb") -> str:
    stamp = ts.strftime("%Y-%m-%d %H:%M:%S.000 UTC")
    return (
        f"{stamp},{user},{db},42,127.0.0.1:5,s,7,SELECT,start,3/44,778,"
        f"{severity},00000,{message},,,,,,,,loc,app,client backend,,1\n"
    )


def _info(tmp_path, name: str) -> LogFileInfo:
    path = tmp_path / name
    return LogFileInfo(name=name, size=path.stat().st_size, modification=BASE)


def _request(tmp_path, files, window_from: datetime,
             window_to: datetime | None = None, **kwargs) -> ScanRequest:
    if window_to is None:
        window_to = window_from + timedelta(hours=1)
    return ScanRequest(
        log_directory=str(tmp_path),
        files=tuple(files),
        window_from_ts=window_from.strftime("%Y-%m-%d %H:%M:%S"),
        window_to_ts=window_to.strftime("%Y-%m-%d %H:%M:%S"),
        recall_clauses=RECALL,
        **kwargs,
    )


def _scan(request: ScanRequest):
    return asyncio.run(BashHarvesterSource(LocalShellTransport()).scan(request))


def test_harvester_equals_local_source(tmp_path) -> None:
    body = _record(BASE + timedelta(seconds=1), "ERROR", "unique one")
    body += "".join(
        _record(BASE + timedelta(seconds=2), "ERROR", "syntax error near X")
        for _ in range(500)
    )
    body += _record(BASE + timedelta(seconds=3), "LOG", "in between noise")
    body += _record(BASE + timedelta(seconds=4), "ERROR", "unique two")
    (tmp_path / "a.csv").write_text(body)
    request = _request(tmp_path, [_info(tmp_path, "a.csv")], BASE)

    remote = _scan(request)
    local = asyncio.run(LocalLogSource(str(tmp_path)).scan(request))

    assert [s.count for s in remote.series] == [s.count for s in local.series] == [1, 500, 1]
    assert [s.first_ts for s in remote.series] == [s.first_ts for s in local.series]
    assert [s.raw_record for s in remote.series] == [s.raw_record for s in local.series]
    assert remote.stats.matched_lines == local.stats.matched_lines == 502


def test_harvester_identity_not_merged(tmp_path) -> None:
    body = _record(BASE + timedelta(seconds=1), "ERROR", "boom", user="alice", db="db1")
    body += _record(BASE + timedelta(seconds=1), "ERROR", "boom", user="bob", db="db2")
    (tmp_path / "a.csv").write_text(body)
    result = _scan(_request(tmp_path, [_info(tmp_path, "a.csv")], BASE))
    assert [s.count for s in result.series] == [1, 1]


def test_harvester_window_bounds(tmp_path) -> None:
    body = "".join(
        _record(BASE - timedelta(seconds=50) + timedelta(seconds=i), "ERROR", "straddle")
        for i in range(100)
    )
    body += _record(BASE + timedelta(minutes=90), "ERROR", "after window")
    (tmp_path / "a.csv").write_text(body)
    result = _scan(
        _request(tmp_path, [_info(tmp_path, "a.csv")], BASE,
                 window_to=BASE + timedelta(minutes=30))
    )
    assert sum(s.count for s in result.series) == 50


def test_harvester_binary_search_on_boundary_file(tmp_path) -> None:
    old = "".join(
        _record(BASE - timedelta(minutes=60) + timedelta(seconds=i), "ERROR", "old")
        for i in range(500)
    )
    fresh = "".join(
        _record(BASE + timedelta(seconds=i), "ERROR", "fresh") for i in range(5)
    )
    (tmp_path / "a.csv").write_text(old + fresh)
    result = _scan(_request(tmp_path, [_info(tmp_path, "a.csv")], BASE))
    assert sum(s.count for s in result.series) == 5
    assert all(b"fresh" in s.raw_record for s in result.series)


def test_harvester_vanished_and_symlink(tmp_path) -> None:
    (tmp_path / "real.csv").write_text(_record(BASE + timedelta(seconds=1), "ERROR", "x"))
    (tmp_path / "evil.csv").symlink_to(tmp_path / "real.csv")
    files = [
        LogFileInfo(name="gone.csv", size=10, modification=BASE),
        LogFileInfo(name="evil.csv", size=10, modification=BASE),
        _info(tmp_path, "real.csv"),
    ]
    result = _scan(_request(tmp_path, files, BASE))
    assert result.stats.files_vanished == 1
    assert result.stats.files_unreadable == 1
    assert result.stats.files_read == 1
    assert sum(s.count for s in result.series) == 1


def test_harvester_invalid_basename_rejected_before_host(tmp_path) -> None:
    (tmp_path / "ok.csv").write_text(_record(BASE + timedelta(seconds=1), "ERROR", "x"))
    files = [
        LogFileInfo(name="../escape.csv", size=10, modification=BASE),
        _info(tmp_path, "ok.csv"),
    ]
    request = _request(tmp_path, files, BASE)
    stats = ScanStats(files_seen=len(files))
    script = build_script(request, stats=stats)
    assert b"escape" not in script
    assert stats.files_unreadable == 1


def test_harvester_wire_budget_stops(tmp_path) -> None:
    body = "".join(
        _record(BASE + timedelta(seconds=i), "ERROR", f"distinct {i} {'y' * 50}")
        for i in range(200)
    )
    (tmp_path / "a.csv").write_text(body)
    result = _scan(
        _request(tmp_path, [_info(tmp_path, "a.csv")], BASE, wire_budget_bytes=2048)
    )
    assert "return_limit_hit" in result.stats.truncation_reasons
    assert result.series


def test_harvester_unterminated_tail_dropped(tmp_path) -> None:
    body = _record(BASE + timedelta(seconds=1), "ERROR", "complete")
    body += _record(BASE + timedelta(seconds=2), "ERROR", "cutoff").rstrip("\n")
    (tmp_path / "a.csv").write_text(body)
    result = _scan(_request(tmp_path, [_info(tmp_path, "a.csv")], BASE))
    assert sum(s.count for s in result.series) == 1
    assert b"complete" in result.series[0].raw_record
    assert result.stats.dropped_lines >= 1


def test_parse_output_rejects_truncated_protocol() -> None:
    stats = ScanStats()
    with pytest.raises(HarvesterProtocolError):
        parse_output(b"CAPS\tv1\tok\tstat-gnu\nRUN\t1\t1\t1\tts\tts\t100\t0\nshort\n",
                     stats=stats)
    stats = ScanStats()
    with pytest.raises(HarvesterProtocolError):
        parse_output(b"CAPS\tv1\tok\tstat-gnu\n", stats=stats)  # no DONE


def test_parse_output_degraded_caps_is_unavailable() -> None:
    with pytest.raises(HarvesterUnavailableError):
        parse_output(b"CAPS\tv1\tdegraded\tmissing-awk\nDONE\t0\tdegraded\n",
                     stats=ScanStats())


def test_harvester_unreadable_file_is_not_a_clean_empty(tmp_path) -> None:
    """mode-000 file: the producer fails while awk exits 0 (no pipefail in sh);
    the side-channel must turn that into files_unreadable, never a clean read."""
    import os
    path = tmp_path / "a.csv"
    path.write_text(_record(BASE + timedelta(seconds=1), "ERROR", "hidden"))
    os.chmod(path, 0)
    try:
        result = _scan(_request(tmp_path, [_info(tmp_path, "a.csv")], BASE))
    finally:
        os.chmod(path, 0o600)
    assert result.stats.files_read == 0
    assert result.stats.files_unreadable == 1
    assert "files_unreadable" in result.stats.truncation_reasons
    assert result.series == []


def test_harvester_wire_budget_includes_frame_overhead(tmp_path) -> None:
    body = "".join(
        _record(BASE + timedelta(seconds=i), "ERROR", f"distinct {i}") for i in range(50)
    )
    (tmp_path / "a.csv").write_text(body)
    request = _request(tmp_path, [_info(tmp_path, "a.csv")], BASE, wire_budget_bytes=1600)
    stats = ScanStats(files_seen=1)
    script = build_script(request, stats=stats)
    proc_result = asyncio.run(LocalShellTransport().run_script_bytes(script, timeout=30))
    assert len(proc_result.stdout) <= 1600  # frames + payloads stay within budget


def test_parse_output_drops_series_on_identity_change() -> None:
    stats = ScanStats(files_seen=1)
    out = (
        b"CAPS\tv1\tok\tstat-gnu\n"
        b"FILE\ta.csv\t100\t10\t20\n"
        b"RUN\t1\t1\t1\tts\tts\t4\t0\nboom\n"
        b"META\ta.csv\t1\t1\t0\t0\n"
        b"FILE_END\ta.csv\t10\t99\t100\n"  # inode changed
        b"DONE\t100\t-\n"
    )
    result = parse_output(out, stats=stats)
    assert result.series == []
    assert "rotation_race" in stats.truncation_reasons


def test_parse_output_drops_series_on_truncation() -> None:
    stats = ScanStats(files_seen=1)
    out = (
        b"CAPS\tv1\tok\tstat-gnu\n"
        b"FILE\ta.csv\t100\t10\t20\n"
        b"RUN\t1\t1\t1\tts\tts\t4\t0\nboom\n"
        b"META\ta.csv\t1\t1\t0\t0\n"
        b"FILE_END\ta.csv\t10\t20\t50\n"  # same inode, size shrank
        b"DONE\t100\t-\n"
    )
    result = parse_output(out, stats=stats)
    assert result.series == []
    assert "rotation_race" in stats.truncation_reasons


def test_parse_output_producer_error_discards_file() -> None:
    stats = ScanStats(files_seen=1)
    out = (
        b"CAPS\tv1\tok\tstat-gnu\n"
        b"FILE\ta.csv\t100\t10\t20\n"
        b"RUN\t1\t1\t1\tts\tts\t4\t0\nboom\n"
        b"META\ta.csv\t1\t1\t0\t0\n"
        b"ERR\tproducer\ta.csv\trc1\n"
        b"FILE_END\ta.csv\t10\t20\t100\n"
        b"DONE\t100\t-\n"
    )
    result = parse_output(out, stats=stats)
    assert result.series == []
    assert stats.files_read == 0
    assert stats.files_unreadable == 1
