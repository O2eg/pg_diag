"""Log directory discovery (logs mode): CSV record boundaries, probes, anchoring."""

from __future__ import annotations

import asyncio
import csv
import io
import os
import subprocess
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from pg_diag.logscan import directory as directory_module
from pg_diag.logscan.clock import LogClock, window_bounds
from pg_diag.logscan.csvparse import csv_format_from_columns, parse_record
from pg_diag.logscan.directory import (
    DirectoryUnavailable,
    HarvesterLogDirectoryProbe,
    LocalLogDirectoryProbe,
    ProbeResult,
    last_record_timestamp,
    parse_probe_output,
    resolve_clock,
    resolve_directory_window,
    verify_discovery,
)
from pg_diag.logscan.harvester import HarvesterProtocolError, HarvesterUnavailableError
from pg_diag.logscan.model import MAX_CANDIDATE_FILES, ProbedFile
from pg_diag.logscan.records import complete_records, plausible_record_start

BASE = datetime(2026, 9, 5, 10, 0, 0)


class LocalShellTransport:
    """Runs the probe scripts through the local /bin/sh (test double)."""

    async def run_script_bytes(self, script, *, arguments=(), timeout, output_limit_bytes=None):
        proc = subprocess.run(
            ["/bin/sh", "-s", "--", *arguments],
            input=script,
            capture_output=True,
            timeout=timeout,
        )
        return SimpleNamespace(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def _record(
    ts: datetime,
    severity: str = "LOG",
    message: str = "noise",
    *,
    columns: int = 26,
    sql_state: str = "00000",
    zone: str = "MSK",
) -> str:
    fields = [
        ts.strftime("%Y-%m-%d %H:%M:%S.000 ") + zone,
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
    ]
    if columns >= 24:
        fields.append("client backend")
    if columns >= 26:
        fields.extend(["", "7"])
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerow(fields)
    return output.getvalue()


def _stamp(ts: datetime, zone: str = "MSK") -> str:
    return ts.strftime("%Y-%m-%d %H:%M:%S.000 ") + zone


PROBES = {
    "local": lambda: LocalLogDirectoryProbe(),
    "remote": lambda: HarvesterLogDirectoryProbe(LocalShellTransport()),
}


def _probe(kind: str, tmp_path) -> ProbeResult:
    return asyncio.run(PROBES[kind]().probe(str(tmp_path)))


def _discover(kind: str, tmp_path, depth_minutes: int = 30, log_timezone=None):
    probe = PROBES[kind]()
    result = asyncio.run(probe.probe(str(tmp_path)))
    state = asyncio.run(
        verify_discovery(
            probe,
            result,
            log_directory=str(tmp_path),
            depth_minutes=depth_minutes,
            clock_for=lambda ts: resolve_clock(ts, log_timezone),
        )
    )
    return resolve_directory_window(
        result,
        log_directory=str(tmp_path),
        depth_minutes=depth_minutes,
        state=state,
        log_timezone=log_timezone,
    )


# --- CSV record boundaries -----------------------------------------------------


def test_complete_records_follow_quote_parity_not_physical_lines() -> None:
    first = _record(BASE, "LOG", "first\n2027-01-01 12:00:00.000 MSK,planted,line\nend")
    second = _record(BASE + timedelta(seconds=1), "ERROR", "second")
    data = (first + second).encode()
    ranges, parity = complete_records(data, partial_first_line=False)
    assert parity is False
    assert [data[start:end] for start, end in ranges] == [first.encode(), second.encode()]
    last, consistent = last_record_timestamp(data, partial_first_line=False)
    assert (last, consistent) == (_stamp(BASE + timedelta(seconds=1)), True)


def test_last_record_timestamp_rejects_chunks_that_start_inside_a_quoted_field() -> None:
    body = _record(BASE, "LOG", "part A\n2027-01-01 12:00:00.000 MSK,planted,line\npart B")
    data = body.encode()
    inside = data.index(b"part A\n") + len(b"part A\n")
    last, consistent = last_record_timestamp(data[inside - 3 :], partial_first_line=True)
    assert consistent is False  # parity ends odd: the chunk began inside quotes
    assert last == "2027-01-01 12:00:00.000 MSK"  # exactly the value that must not be trusted
    exact, consistent = last_record_timestamp(
        data[inside - 3 :], partial_first_line=True, initial_parity=True
    )
    assert (exact, consistent) == (None, True)
    unterminated = data + b"2026-09-05 10:00:09.000 MSK,alice,appdb"
    last, consistent = last_record_timestamp(unterminated, partial_first_line=False)
    assert (last, consistent) == (_stamp(BASE), True)


def test_partial_first_line_quotes_move_parity_for_every_cut_point() -> None:
    # Cut the file at every byte: with the exact prefix parity the last record
    # must always be the real one, never the planted date inside the message.
    planted = "2027-01-01 12:00:00.000 MSK,alice,appdb,42,c,s,7,SELECT,start,3/44,778,LOG,00000,fake"
    body = _record(BASE - timedelta(minutes=1), "ERROR", "real error")
    body += _record(BASE, "LOG", 'quoted "part" A\n' + planted + "\nend of message")
    data = body.encode()
    for cut in range(1, len(data)):
        parity = bool(data[:cut].count(b'"') % 2)
        last, _consistent = last_record_timestamp(
            data[cut:], partial_first_line=True, initial_parity=parity
        )
        assert last in (None, _stamp(BASE)), (cut, last)
    assert plausible_record_start(data) is True
    inside = data.index(b"quoted")
    assert plausible_record_start(data[inside:]) is False


def test_csv_format_from_columns_and_locale() -> None:
    for columns, version, label in ((23, 120000, "10-12"), (24, 130000, "13"), (26, 140000, "14+")):
        fmt = csv_format_from_columns(columns, "LOG")
        assert fmt is not None and (fmt.columns, fmt.server_version_num) == (columns, version)
        assert label in fmt.label and fmt.locale_supported
    assert csv_format_from_columns(25, "LOG") is None
    localized = csv_format_from_columns(26, "ОШИБКА")
    assert localized is not None and localized.locale_supported is False


# --- probes (both transports) ---------------------------------------------------


def _write_directory(tmp_path) -> None:
    old = "".join(
        _record(BASE - timedelta(hours=3) + timedelta(seconds=i), "ERROR", f"old {i}")
        for i in range(300)
    )
    (tmp_path / "postgresql-2026-09-05_070000.csv").write_text(old)
    fresh = "".join(
        _record(BASE - timedelta(minutes=30) + timedelta(seconds=i), "LOG", "noise")
        for i in range(100)
    )
    fresh += _record(BASE - timedelta(minutes=5), "ERROR", "fresh error")
    fresh += _record(BASE, "WARNING", "last warning")
    (tmp_path / "postgresql-2026-09-05_093000.csv").write_text(fresh)
    (tmp_path / "empty.csv").write_text("")
    (tmp_path / "notes.txt").write_text("ignored")
    os.utime(tmp_path / "postgresql-2026-09-05_070000.csv", (1_000_000, 1_000_000))
    os.utime(tmp_path / "postgresql-2026-09-05_093000.csv", (2_000_000, 2_000_000))
    os.utime(tmp_path / "empty.csv", (500_000, 500_000))


def test_local_and_remote_probes_agree(tmp_path) -> None:
    _write_directory(tmp_path)
    local = _probe("local", tmp_path)
    remote = _probe("remote", tmp_path)
    assert local.total_files == remote.total_files == 3
    assert not local.listing_truncated and not remote.listing_truncated
    by_local = {f.name: f for f in local.files}
    by_remote = {f.name: f for f in remote.files}
    assert set(by_local) == set(by_remote) == {
        "postgresql-2026-09-05_070000.csv",
        "postgresql-2026-09-05_093000.csv",
        "empty.csv",
    }
    for name, probed in by_local.items():
        other = by_remote[name]
        assert (probed.size, probed.last_ts, probed.columns, probed.severity, probed.determined) == (
            other.size, other.last_ts, other.columns, other.severity, other.determined
        )
        assert int(probed.mtime) == int(other.mtime)  # the shell reports whole seconds
    fresh = by_local["postgresql-2026-09-05_093000.csv"]
    assert (fresh.last_ts, fresh.columns, fresh.severity) == (_stamp(BASE), 26, "LOG")
    assert by_local["empty.csv"].last_ts is None and by_local["empty.csv"].columns is None
    assert [f.name for f in local.files][:2] == [
        "postgresql-2026-09-05_093000.csv",
        "postgresql-2026-09-05_070000.csv",
    ]


@pytest.mark.parametrize("kind", ["local", "remote"])
def test_planted_date_inside_a_message_does_not_move_the_window(kind, tmp_path) -> None:
    body = _record(BASE - timedelta(minutes=5), "ERROR", "real error", sql_state="42601")
    body += _record(
        BASE,
        "LOG",
        "statement: select 1\n2027-01-01 12:00:00.000 MSK,alice,appdb,42,c,s,7,SELECT,start,"
        "3/44,778,LOG,00000,fake\nend of message",
    )
    (tmp_path / "a.csv").write_text(body)
    window = _discover(kind, tmp_path)
    assert window.window_to == "2026-09-05 10:00:00.000"
    assert window.inventory["source"]["anchor_verified"] is True
    assert not window.truncation_reasons


@pytest.mark.parametrize("kind", ["local", "remote"])
def test_anchor_verification_uses_exact_parity_when_the_tail_parse_is_fooled(kind, tmp_path) -> None:
    # A quoted message longer than the tail probe, ending in an unterminated
    # record: the parity-assuming tail parse cannot detect that it started
    # inside quotes, but the anchor verification counts quotes from byte 0.
    planted = "2027-01-01 12:00:00.000 MSK,alice,appdb,42,c,s,7,SELECT,start,3/44,778,LOG,00000,fake"
    long_message = ("filler line\n" * 2000) + planted + "\n" + ("filler line\n" * 200)
    body = _record(BASE - timedelta(minutes=1), "ERROR", "real error", sql_state="42601")
    body += _record(BASE, "LOG", long_message)
    # The in-flight record has flushed its first line (opening quote) only, so a
    # parse that assumed even parity at the chunk start closes evenly and is
    # fooled by the planted line.
    body += _stamp(BASE + timedelta(seconds=5)) + (
        ',alice,appdb,42,c,s,7,SELECT,start,3/44,778,LOG,00000,"in-flight line 1\n'
    )
    (tmp_path / "a.csv").write_text(body)
    probed = _probe(kind, tmp_path)
    assert probed.files[0].last_ts == "2027-01-01 12:00:00.000 MSK"  # the fooled tail parse
    window = _discover(kind, tmp_path)
    assert window.window_to == "2026-09-05 10:00:00.000"
    assert window.inventory["source"]["anchor_verified"] is True


@pytest.mark.parametrize("kind", ["local", "remote"])
def test_long_last_record_is_still_found_within_the_probe_cap(kind, tmp_path) -> None:
    plan = "duration: 99.0 ms  plan:\n" + ("x" * 100 + "\n") * 12000  # ~1.2 MiB record
    body = _record(BASE - timedelta(minutes=1), "ERROR", "before") + _record(BASE, "LOG", plan)
    (tmp_path / "a.csv").write_text(body)
    probed = _probe(kind, tmp_path)
    assert probed.files[0].last_ts == _stamp(BASE) and probed.files[0].determined


@pytest.mark.parametrize("kind", ["local", "remote"])
def test_undetermined_file_is_scanned_and_marks_discovery_incomplete(kind, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(directory_module, "MAX_PROBE_BYTES", 65_536)
    plan = "duration: 99.0 ms  plan:\n" + ("x" * 100 + "\n") * 2000  # exceeds the patched cap
    body = _record(BASE - timedelta(minutes=1), "ERROR", "before") + _record(BASE, "LOG", plan)
    (tmp_path / "long.csv").write_text(body)
    (tmp_path / "short.csv").write_text(_record(BASE - timedelta(minutes=2), "LOG", "noise"))
    probed = _probe(kind, tmp_path)
    long = next(f for f in probed.files if f.name == "long.csv")
    assert long.last_ts is None and long.determined is False
    window = _discover(kind, tmp_path)
    assert "discovery_incomplete" in window.truncation_reasons
    assert [c.name for c in window.candidates] == ["long.csv", "short.csv"]
    assert window.inventory["source"]["files_undetermined"] == 1


@pytest.mark.parametrize("kind", ["local", "remote"])
def test_long_first_record_still_detects_the_layout(kind, tmp_path) -> None:
    body = _record(BASE - timedelta(minutes=5), "LOG", "statement: " + "x" * 5000, columns=24)
    body += _record(BASE, "ERROR", "later error", columns=24)
    (tmp_path / "a.csv").write_text(body)
    probed = _probe(kind, tmp_path)
    assert (probed.files[0].columns, probed.files[0].severity) == (24, "LOG")
    assert _discover(kind, tmp_path).csv_format.server_version_num == 130000


def test_probes_report_unreadable_symlink_and_unsafe_names(tmp_path) -> None:
    (tmp_path / "a.csv").write_text(_record(BASE, "ERROR", "x"))
    (tmp_path / "link.csv").symlink_to(tmp_path / "a.csv")
    (tmp_path / "secret.csv").write_text(_record(BASE, "ERROR", "hidden"))
    (tmp_path / "secret.csv").chmod(0)
    (tmp_path / "bad name.csv").write_text(_record(BASE, "ERROR", "space"))
    if os.geteuid() == 0:
        pytest.skip("root reads mode-000 files")
    try:
        local = _probe("local", tmp_path)
        remote = _probe("remote", tmp_path)
    finally:
        (tmp_path / "secret.csv").chmod(0o600)
    assert sorted(f.name for f in local.files) == ["a.csv", "bad name.csv"]
    assert sorted(local.unreadable) == ["link.csv", "secret.csv"]
    assert [f.name for f in remote.files] == ["a.csv"]
    assert sorted(remote.unreadable) == ["<skipped>", "<skipped>", "secret.csv"]


def test_remote_probe_protocol_errors_and_degraded_caps(tmp_path) -> None:
    with pytest.raises(HarvesterUnavailableError):
        parse_probe_output(b"CAPS\tv3\tdegraded\tmissing-awk\nDONE\t0\t0\n")
    with pytest.raises(HarvesterProtocolError):
        parse_probe_output(b"CAPS\tv3\tok\tstat-gnu\nFILE\ta.csv\t10\t-\t-\n")
    with pytest.raises(HarvesterProtocolError):
        parse_probe_output(
            b"CAPS\tv3\tok\tstat-gnu\nFILE\t../x.csv\t1\t-\t-\t1\t0\t0\t26\tLOG\nDONE\t1\t0\n"
        )
    with pytest.raises(DirectoryUnavailable):
        parse_probe_output(b"CAPS\tv3\tok\tstat-gnu\nERR\tnodir\t-\nDONE\t0\t0\n")
    with pytest.raises(HarvesterProtocolError):
        parse_probe_output(b"CAPS\tv3\tok\tstat-gnu\n")
    parsed = parse_probe_output(
        b"CAPS\tv3\tok\tstat-gnu\nFILE\ta.csv\t10\t5\t2026-09-05 10:00:00.000 MSK\t1\t0\t1\t26\tLOG\nDONE\t1\t0\n"
    )
    probed = parsed.files[0]
    assert (probed.last_ts, probed.determined, probed.exact, probed.trusted) == (
        _stamp(BASE), True, False, True
    )
    with pytest.raises(DirectoryUnavailable):
        asyncio.run(HarvesterLogDirectoryProbe(LocalShellTransport()).probe(str(tmp_path / "no")))


# --- window resolution -------------------------------------------------------------


def _probed(name: str, last: datetime | None, *, columns: int | None = 26, size=100, determined=True):
    return ProbedFile(
        name=name,
        size=size,
        mtime=None,
        last_ts=last.strftime("%Y-%m-%d %H:%M:%S.123 MSK") if last else None,
        columns=columns,
        severity="LOG" if columns else None,
        determined=determined,
    )


def _resolve(files, *, unreadable=(), total=None, truncated=False, depth=20, **kwargs):
    result = ProbeResult(
        files=list(files),
        unreadable=list(unreadable),
        total_files=total if total is not None else len(files) + len(unreadable),
        listing_truncated=truncated,
    )
    return resolve_directory_window(result, log_directory="/var/log/pg", depth_minutes=depth, **kwargs)


def test_resolve_window_anchors_at_newest_record_and_orders_candidates() -> None:
    window = _resolve(
        [
            _probed("older.csv", BASE - timedelta(minutes=15)),
            _probed("newest.csv", BASE),
            _probed("ancient.csv", BASE - timedelta(days=2)),
            _probed("empty.csv", None, columns=None, size=0),
        ]
    )
    assert window.window_to == "2026-09-05 10:00:00.123"
    assert window.window_from == "2026-09-05 09:40:00"
    assert [f.name for f in window.candidates] == ["newest.csv", "older.csv"]
    assert window.candidates[-1].modification == BASE - timedelta(minutes=15, milliseconds=-123)
    assert window.truncation_reasons == frozenset()
    assert window.csv_format.columns == 26
    assert window.file_versions == {n: 140000 for n in ("older.csv", "newest.csv", "ancient.csv")}
    assert window.locale_supported is True
    inventory = window.inventory
    assert inventory["window_from"] == "2026-09-05 09:40:00"
    assert inventory["collected_to"] == "2026-09-05 10:00:00.123"
    settings = inventory["settings"]
    assert settings["log_directory"] == "/var/log/pg"
    assert settings["log_timezone"] == "MSK" and settings["log_utc_offset_seconds"] is None
    assert settings["block_size"] is None
    files = {row["name"]: row for row in inventory["files"]}
    assert files["newest.csv"]["is_newest"] and files["newest.csv"]["in_window"]
    assert all(row["is_current"] is False for row in files.values())  # active file unknown
    assert files["older.csv"]["in_window"] and not files["ancient.csv"]["in_window"]
    assert files["empty.csv"]["modification"] is None and files["empty.csv"]["csv_columns"] is None
    assert inventory["file_count_total"] == 4
    assert inventory["source"]["anchor_verified"] is False  # no verification state given


def test_resolve_window_resolves_zone_from_suffix_or_option() -> None:
    numeric = ProbedFile("a.csv", 10, None, "2026-09-05 10:00:00.000 +03", 26, "LOG")
    window = _resolve([numeric])
    assert window.inventory["settings"]["log_utc_offset_seconds"] == 3 * 3600
    assert window.inventory["settings"]["log_timezone"] == "+03"
    utc = ProbedFile("a.csv", 10, None, "2026-09-05 10:00:00.000 UTC", 26, "LOG")
    assert _resolve([utc]).inventory["settings"]["log_utc_offset_seconds"] == 0
    named = _resolve([_probed("a.csv", BASE)], log_timezone="Europe/Moscow")
    assert named.inventory["settings"]["log_timezone"] == "Europe/Moscow"
    assert named.inventory["settings"]["log_utc_offset_seconds"] == 3 * 3600
    old_layout = _probed("pg12.csv", BASE - timedelta(minutes=5), columns=23)
    mixed = _resolve([old_layout, _probed("pg16.csv", BASE)])
    assert mixed.file_versions == {"pg12.csv": 120000, "pg16.csv": 140000}
    assert mixed.csv_format.columns == 26


def test_resolve_window_reports_every_discovery_gap_as_incomplete() -> None:
    files = [_probed(f"f{i:03d}.csv", BASE - timedelta(seconds=i)) for i in range(MAX_CANDIDATE_FILES + 5)]
    window = _resolve(files)
    assert len(window.candidates) == MAX_CANDIDATE_FILES
    assert "candidate_limit_hit" in window.truncation_reasons

    unreadable = _resolve([_probed("a.csv", BASE)], unreadable=["old-but-who-knows.csv"])
    assert unreadable.truncation_reasons == frozenset({"files_unreadable"})
    assert unreadable.files_unreadable == 1

    truncated = _resolve([_probed("a.csv", BASE)], total=2000, truncated=True)
    assert "candidate_limit_hit" in truncated.truncation_reasons  # hidden files may hold records

    undetermined = _resolve([_probed("a.csv", BASE), _probed("huge.csv", None, determined=False)])
    assert "discovery_incomplete" in undetermined.truncation_reasons
    assert [c.name for c in undetermined.candidates] == ["huge.csv", "a.csv"]

    localized = ProbedFile("ru.csv", 10, None, _stamp(BASE), 26, "ОШИБКА")
    assert _resolve([localized]).locale_supported is False


def test_resolve_window_unavailable_cases() -> None:
    with pytest.raises(DirectoryUnavailable, match="no csvlog files"):
        _resolve([])
    with pytest.raises(DirectoryUnavailable, match="no complete csvlog record") as info:
        _resolve([_probed("empty.csv", None, columns=None, size=0)])
    assert info.value.inventory["files"][0]["name"] == "empty.csv"
    odd = ProbedFile("odd.csv", 5, None, "2026-09-05 10:00:00 UTC", 3, None)
    with pytest.raises(DirectoryUnavailable, match="cannot detect the csvlog layout") as info:
        _resolve([odd])
    assert info.value.inventory["settings"]["log_timezone"] == "UTC"


def test_parse_record_honours_per_layout_columns() -> None:
    old = parse_record(_record(BASE, "ERROR", "x", columns=23).encode(), server_version_num=120000)
    new = parse_record(_record(BASE, "ERROR", "x", columns=26).encode(), server_version_num=140000)
    assert old is not None and old.backend_type is None and old.query_id is None and not old.partial
    assert new is not None and new.backend_type == "client backend" and new.query_id == 7


# --- review round 2: exclusion safety, DST windows, budgets -----------------------


def _planted_old_file(tmp_path, name: str = "victim.csv") -> None:
    """Fresh errors, then a long message with a planted OLD date, then an
    in-flight record whose first line is flushed: the assumed-parity tail parse
    is consistent yet reports the planted date."""
    old = "2026-09-05 07:00:00.000 MSK,alice,appdb,42,c,s,7,SELECT,start,3/44,778,LOG,00000,fake"
    body = _record(BASE, "ERROR", "fresh error 10:00", sql_state="42601")
    body += _record(BASE + timedelta(minutes=1), "ERROR", "fresh error 10:01", sql_state="42601")
    body += _record(BASE + timedelta(seconds=90), "LOG", ("filler\n" * 3000) + old + "\n" + ("filler\n" * 10))
    body += _stamp(BASE + timedelta(seconds=100)) + (
        ',alice,appdb,42,c,s,7,SELECT,start,3/44,778,LOG,00000,"in-flight line 1\n'
    )
    (tmp_path / name).write_text(body)


@pytest.mark.parametrize("kind", ["local", "remote"])
def test_untrusted_old_date_cannot_exclude_a_file_from_the_window(kind, tmp_path) -> None:
    _planted_old_file(tmp_path)
    (tmp_path / "newer.csv").write_text(_record(BASE + timedelta(minutes=2), "LOG", "noise"))
    probed = _probe(kind, tmp_path)
    victim = next(f for f in probed.files if f.name == "victim.csv")
    assert victim.last_ts == "2026-09-05 07:00:00.000 MSK" and not victim.trusted
    window = _discover(kind, tmp_path, depth_minutes=10)
    assert [c.name for c in window.candidates] == ["newer.csv", "victim.csv"]
    assert window.inventory["source"]["files_verified"] == 2  # anchor + the excluded candidate
    assert not window.truncation_reasons


def test_exclusion_verification_stops_at_the_budget_and_reports_incomplete(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(directory_module, "VERIFY_BUDGET_BYTES", 1)
    _planted_old_file(tmp_path)
    (tmp_path / "newer.csv").write_text(_record(BASE + timedelta(minutes=2), "LOG", "noise"))
    window = _discover("local", tmp_path, depth_minutes=10)
    assert "discovery_incomplete" in window.truncation_reasons
    assert [c.name for c in window.candidates] == ["newer.csv"]  # excluded but reported incomplete
    assert window.inventory["source"]["anchor_verified"] is False


@pytest.mark.parametrize("kind", ["local", "remote"])
def test_trusted_tail_parse_skips_verification_for_ordinary_archives(kind, tmp_path) -> None:
    for index in range(3):
        stamp = BASE - timedelta(hours=index + 1)
        body = "".join(_record(stamp + timedelta(seconds=i), "LOG", "noise " * 400) for i in range(60))
        (tmp_path / f"archive-{index}.csv").write_text(body)
    (tmp_path / "current.csv").write_text(_record(BASE, "ERROR", "now"))
    probed = _probe(kind, tmp_path)
    archives = [f for f in probed.files if f.name.startswith("archive")]
    assert all(f.trusted and not f.exact for f in archives)  # bigger than one tail chunk
    window = _discover(kind, tmp_path, depth_minutes=10)
    assert window.inventory["source"]["files_verified"] == 1  # only the anchor
    assert [c.name for c in window.candidates] == ["current.csv"]


@pytest.mark.parametrize("kind", ["local", "remote"])
def test_first_field_larger_than_the_csv_module_default_is_recognized(kind, tmp_path) -> None:
    body = _record(BASE - timedelta(minutes=1), "LOG", "statement: " + "x" * 150_000)
    body += _record(BASE, "ERROR", "after big field")
    (tmp_path / "a.csv").write_text(body)
    probed = _probe(kind, tmp_path)
    assert (probed.files[0].columns, probed.files[0].severity) == (26, "LOG")
    assert _discover(kind, tmp_path).csv_format.columns == 26


def test_window_bounds_are_absolute_across_a_dst_transition() -> None:
    berlin = LogClock(label="Europe/Berlin", zone=resolve_clock(None, "Europe/Berlin").zone)
    spring = window_bounds("2026-03-29 03:05:00.000 CEST", 10, berlin)
    assert spring.window_from == "2026-03-29 01:55:00"  # 7 minutes before, one hour earlier on the wall
    assert spring.scan_from <= "2026-03-29 01:55:00"
    assert (spring.anchor_abs - spring.from_abs).total_seconds() == 600
    fall = window_bounds("2026-10-25 02:05:00.000 CET", 10, berlin)
    assert fall.window_from == "2026-10-25 02:55:00"  # the repeated hour, still CEST
    assert fall.scan_from <= "2026-10-25 01:55:00"  # widened so the string scanner keeps 02:55 CEST
    assert fall.scan_to == "2026-10-25 03:05:00.000"  # and 02:58 CEST, which reads later than the anchor
    assert spring.scan_to == "2026-03-29 04:05:00.000"
    assert berlin.offset_for(datetime(2026, 10, 25, 2, 30), "CEST") == 7200
    assert berlin.offset_for(datetime(2026, 10, 25, 2, 30), "CET") == 3600
    naive = window_bounds("2026-03-29 03:05:00.000 MSK", 10, LogClock(label="MSK"))
    assert naive.window_from == naive.scan_from == "2026-03-29 02:55:00"
    assert naive.scan_to == naive.window_to and naive.anchor_abs is None


@pytest.mark.parametrize("kind", ["local", "remote"])
def test_anchor_is_the_absolute_newest_file_across_a_fall_back(kind, tmp_path) -> None:
    (tmp_path / "cest.csv").write_text(_record(datetime(2026, 10, 25, 2, 58), "ERROR", "x", zone="CEST"))
    (tmp_path / "cet.csv").write_text(_record(datetime(2026, 10, 25, 2, 5), "ERROR", "y", zone="CET"))
    window = _discover(kind, tmp_path, depth_minutes=10, log_timezone="Europe/Berlin")
    assert window.anchor_ts == "2026-10-25 02:05:00.000 CET"
    assert window.window_to == "2026-10-25 02:05:00.000"
    assert [c.name for c in window.candidates] == ["cet.csv", "cest.csv"]
    assert window.inventory["files"][0]["name"] == "cet.csv"  # ordering follows absolute time too
    naive = _discover(kind, tmp_path, depth_minutes=10)  # no zone: wall clock, CEST looks newer
    assert naive.anchor_ts == "2026-10-25 02:58:00.000 CEST"
