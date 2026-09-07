"""Log directory discovery without a database (logs mode).

``one-shot``/``snapshots`` discover csvlog files through ``pg_ls_logdir()``
and anchor the window at the server clock. The ``logs`` command has neither:
it probes the ``*.csv`` files in a directory directly and anchors the window
at the newest complete record, so copied or archived logs analyze exactly
like live ones.

Record boundaries are CSV boundaries, not physical lines: a csvlog field can
contain newlines, so a line that merely starts with a date may sit inside a
quoted message. Both probes track quote parity while scanning, including the
quotes of the partial line a tail chunk begins with. A tail probe starts from
an arbitrary offset with parity assumed even; the parse is accepted only when
parity is even again at the end of the chunk, which a start inside a quoted
field cannot produce (quotes inside fields are always doubled), otherwise the
probe doubles its reach.

Two decisions rest on these timestamps and get stronger evidence:

* the file that anchors the window is re-checked with exact parity counted
  from its first byte (a chunk that started inside a quoted field of a file
  that also ends inside an unfinished record can fool the assumed parity);
* a file is excluded from the window only on an exact timestamp (parsed from
  byte 0 or verified) or a *trusted* one — parity closes, the last complete
  record ends at the file's final newline, and every record starts with a
  timestamp; other candidates for exclusion are verified within a byte
  budget, and past the budget the window is reported incomplete.

Two probe transports share one result model: :class:`LocalLogDirectoryProbe`
(pure Python on the collector) and :class:`HarvesterLogDirectoryProbe` (one
POSIX-sh script over SSH per phase, mirroring the scan harvester's protocol).
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, BinaryIO
from zoneinfo import ZoneInfo

from .clock import LogClock, WindowBounds, window_bounds, zone_suffix
from .csvparse import CsvFormat, csv_format_from_columns, first_record_fields, parse_timestamp
from .harvester import HarvesterProtocolError, HarvesterUnavailableError
from .model import (
    HEAD_PROBE_BYTES,
    MAX_CANDIDATE_FILES,
    MAX_PROBE_BYTES,
    MAX_PROBE_FILES,
    PHASE_WALLCLOCK_SECONDS,
    REASON_CANDIDATE_LIMIT,
    REASON_DISCOVERY_INCOMPLETE,
    REASON_UNREADABLE,
    TAIL_PROBE_BYTES,
    VERIFY_BUDGET_BYTES,
    LogFileInfo,
    ProbedFile,
)
from .records import complete_records, parse_tail

PROBE_PROTOCOL_VERSION = "v3"
_PROBE_TIMEOUT_SECONDS = PHASE_WALLCLOCK_SECONDS / 2
_BASENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.csv$")
_NUMERIC_TZ_RE = re.compile(r"^[+-]\d{2}(?::?\d{2})?$")
_UTC_LABELS = frozenset({"UTC", "GMT", "Z", "UCT", "Zulu"})
_COUNT_CHUNK = 1 << 20


@dataclass
class ProbeResult:
    files: list[ProbedFile]
    unreadable: list[str]  # names that could not be probed (permissions, symlinks)
    total_files: int  # *.csv entries seen, including the ones beyond the probe cap
    listing_truncated: bool


@dataclass(frozen=True)
class DirectoryWindow:
    bounds: WindowBounds
    clock: LogClock
    anchor_ts: str  # raw timestamp of the newest complete record (with suffix)
    candidates: tuple[LogFileInfo, ...]  # undetermined files first, then newest first
    csv_format: CsvFormat
    file_versions: dict[str, int]
    locale_supported: bool
    files_unreadable: int
    truncation_reasons: frozenset[str]
    inventory: dict[str, Any]

    @property
    def window_from(self) -> str:
        return self.bounds.window_from

    @property
    def window_to(self) -> str:
        return self.bounds.window_to

    @property
    def scan_from(self) -> str:
        return self.bounds.scan_from

    @property
    def scan_to(self) -> str:
        return self.bounds.scan_to


class DirectoryUnavailable(Exception):
    """No usable csvlog files; ``inventory`` still describes what was found."""

    def __init__(self, message: str, *, inventory: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.inventory = inventory


class LogDirectoryProbe:
    async def probe(self, log_directory: str) -> ProbeResult:
        raise NotImplementedError

    async def verify_last_ts(self, log_directory: str, name: str) -> tuple[str | None, int]:
        """Exact last record timestamp and the bytes read to establish it.

        Returns ``(None, bytes)`` when the file holds no complete record;
        raises ``OSError`` when it cannot be read.
        """
        raise NotImplementedError


# --- quote-parity record scanning: see records.py ---------------------------


def last_record_timestamp(
    data: bytes,
    *,
    partial_first_line: bool,
    initial_parity: bool = False,
) -> tuple[str | None, bool]:
    """(timestamp of the last complete record, parse consistent)."""
    parsed = parse_tail(
        data, partial_first_line=partial_first_line, initial_parity=initial_parity
    )
    return parsed.last_ts, parsed.consistent


# --- local transport ---------------------------------------------------------


class LocalLogDirectoryProbe(LogDirectoryProbe):
    """Direct directory listing plus head/tail reads on the collector."""

    async def probe(self, log_directory: str) -> ProbeResult:
        return await asyncio.to_thread(self._probe_sync, log_directory)

    async def verify_last_ts(self, log_directory: str, name: str) -> tuple[str | None, int]:
        return await asyncio.to_thread(self._verify_sync, log_directory, name)

    def _probe_sync(self, log_directory: str) -> ProbeResult:
        entries: list[tuple[str, float]] = []
        unreadable: list[str] = []
        with os.scandir(log_directory) as scanner:
            for entry in scanner:
                if not entry.name.endswith(".csv"):
                    continue
                try:
                    if entry.is_symlink():
                        unreadable.append(entry.name)  # refused, like the scan
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    stat = entry.stat(follow_symlinks=False)
                except OSError:
                    unreadable.append(entry.name)
                    continue
                entries.append((entry.name, stat.st_mtime))
        # Modification time only ranks which files to probe first; it never
        # proves anything about record times (copied archives keep no order).
        entries.sort(key=lambda row: (-row[1], row[0]))
        total_files = len(entries) + len(unreadable)
        files: list[ProbedFile] = []
        for name, mtime in entries[:MAX_PROBE_FILES]:
            probed = self._probe_file(log_directory, name, mtime)
            if probed is None:
                unreadable.append(name)
            else:
                files.append(probed)
        return ProbeResult(
            files=files,
            unreadable=unreadable,
            total_files=total_files,
            listing_truncated=len(entries) > MAX_PROBE_FILES,
        )

    @staticmethod
    def _open(log_directory: str, name: str) -> BinaryIO:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        return os.fdopen(os.open(os.path.join(log_directory, name), flags), "rb")

    def _probe_file(self, log_directory: str, name: str, mtime: float) -> ProbedFile | None:
        try:
            handle = self._open(log_directory, name)
        except OSError:
            return None
        try:
            size = os.fstat(handle.fileno()).st_size
            columns, severity = _first_record_layout(handle, size)
            last_ts, determined, exact, trusted = _tail_timestamp(handle, size)
        except OSError:
            return None
        finally:
            handle.close()
        return ProbedFile(
            name=name,
            size=size,
            mtime=mtime,
            last_ts=last_ts,
            columns=columns,
            severity=severity,
            determined=determined,
            exact=exact,
            trusted=trusted,
        )

    def _verify_sync(self, log_directory: str, name: str) -> tuple[str | None, int]:
        with self._open(log_directory, name) as handle:
            size = os.fstat(handle.fileno()).st_size
            probe = TAIL_PROBE_BYTES
            while True:
                offset = max(0, size - probe)
                parity = _quote_parity_before(handle, offset)
                handle.seek(offset)
                data = handle.read(size - offset)
                last, _consistent = last_record_timestamp(
                    data, partial_first_line=offset > 0, initial_parity=parity
                )
                if last is not None or offset == 0:
                    return last, offset + len(data)
                probe *= 2


def _quote_parity_before(handle: BinaryIO, offset: int) -> bool:
    """Exact quote parity of ``[0, offset)``: one sequential read of the prefix."""
    handle.seek(0)
    remaining = offset
    quotes = 0
    while remaining > 0:
        chunk = handle.read(min(_COUNT_CHUNK, remaining))
        if not chunk:
            break
        remaining -= len(chunk)
        quotes += chunk.count(b'"')
    return bool(quotes % 2)


def _first_record_layout(handle: BinaryIO, size: int) -> tuple[int | None, str | None]:
    """Column count and severity of the first complete record (doubling head)."""
    probe = HEAD_PROBE_BYTES
    while True:
        handle.seek(0)
        data = handle.read(min(probe, size))
        ranges, _parity = complete_records(data, partial_first_line=False)
        if ranges:
            fields = first_record_fields(data[ranges[0][0] : ranges[0][1]])
            if fields is None:
                return None, None
            return len(fields), fields[11] or None
        if probe >= size or probe >= MAX_PROBE_BYTES:
            return None, None
        probe *= 2


def _tail_timestamp(handle: BinaryIO, size: int) -> tuple[str | None, bool, bool, bool]:
    """(last_ts, determined, exact, trusted) of the tail parse.

    Parity is assumed even at the chunk; the parse is trusted only when parity
    ends even (or the chunk started at byte 0, where parity is known and the
    result is exact); otherwise the probe doubles its reach until
    MAX_PROBE_BYTES, after which the file is reported undetermined.
    """
    probe = TAIL_PROBE_BYTES
    while True:
        offset = max(0, size - probe)
        handle.seek(offset)
        data = handle.read(size - offset)
        parsed = parse_tail(data, partial_first_line=offset > 0)
        if offset == 0:
            return parsed.last_ts, True, True, True
        if parsed.consistent and parsed.last_ts is not None:
            return parsed.last_ts, True, False, parsed.trusted
        if probe >= MAX_PROBE_BYTES:
            return None, False, False, False
        probe *= 2


# --- remote transport (POSIX sh over SSH) ------------------------------------

# awk helpers shared by the probe and the verification script. Single quotes
# are forbidden inside (the program is embedded in single quotes).
_AWK_COMMON = r"""
function quotestate(l, q,   i, ch, len) {
  len = length(l)
  for (i = 1; i <= len; i++) {
    ch = substr(l, i, 1)
    if (ch != "\"") continue
    if (q && substr(l, i + 1, 1) == "\"") { i++; continue }
    q = !q
  }
  return q
}
function tsof(l,   c) {
  if (l !~ /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] /) return ""
  c = index(l, ",")
  if (c <= 1) return ""
  return substr(l, 1, c - 1)
}
"""

# Tail scan: OFF (chunk offset), RANGELEN (chunk length), Q0 (initial parity).
# Prints "<last_ts or -> <consistent 0/1> <trusted 0/1>"; a line is processed
# only after the next one arrives so an unterminated tail is never a record.
# The partial first line cannot start a record but its quotes move parity.
_AWK_TAIL = _AWK_COMMON + r"""
BEGIN { off = ENVIRON["OFF"] + 0; rangelen = ENVIRON["RANGELEN"] + 0
        q = ENVIRON["Q0"] + 0; cum = 0; have_prev = 0; last = ""; rec_ts = ""
        rec_open = 0; allts = 1; anyrec = 0; lastend = -1 }
{ cum += length($0) + 1
  if (have_prev) consider(prev_line, prev_nr, cum - length($0) - 1)
  prev_line = $0; prev_nr = NR; have_prev = 1 }
END { if (have_prev && cum == rangelen) consider(prev_line, prev_nr, cum)
      trusted = (!q && anyrec && lastend == rangelen && allts) ? 1 : 0
      printf "%s %d %d\n", (last == "" ? "-" : last), (q ? 0 : 1), trusted }
function consider(l, n, endpos) {
  if (n == 1 && off > 0) { q = quotestate(l, q); return }
  if (!q) { rec_ts = tsof(l); rec_open = 1 }
  q = quotestate(l, q)
  if (!q && rec_open) {
    anyrec = 1; lastend = endpos
    if (rec_ts == "") allts = 0; else last = rec_ts
    rec_open = 0
  }
}
"""

# Head scan from byte 0: first complete record -> "<columns> <severity>".
_AWK_HEAD = _AWK_COMMON + r"""
BEGIN { q = 0; fld = 0; sev = ""; started = 0; ok = 0 }
{ if (!started) { if (tsof($0) == "") { print "- -"; exit }; started = 1 }
  else { if (q && fld == 11) sev = sev "\n" }
  len = length($0)
  for (i = 1; i <= len; i++) {
    ch = substr($0, i, 1)
    if (q) {
      if (ch == "\"") { if (substr($0, i + 1, 1) == "\"") { if (fld == 11) sev = sev "\""; i++; continue }; q = 0; continue }
      if (fld == 11) sev = sev ch
      continue
    }
    if (ch == "\"") { q = 1; continue }
    if (ch == ",") { fld++; continue }
    if (fld == 11) sev = sev ch
  }
  if (!q) { ok = 1; exit }
}
END { if (ok) printf "%d %s\n", fld + 1, (sev == "" ? "-" : substr(sev, 1, 64)); else print "- -" }
"""

_PROBE_SCRIPT_TEMPLATE = r"""
LC_ALL=C
export LC_ALL
LOGDIR=@LOGDIR@
MAXFILES=@MAXFILES@
HEADMAX=@HEADMAX@
TAILB=@TAILB@
TAILMAX=@TAILMAX@
TAIL_PROG=@TAILPROG@
HEAD_PROG=@HEADPROG@
for tool in awk head tail ls wc; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    printf 'CAPS\t@VERSION@\tdegraded\tmissing-%s\n' "$tool"
    printf 'DONE\t0\t0\n'
    exit 0
  fi
done
if stat -c '%s %Y' "$LOGDIR" >/dev/null 2>&1; then STATFMT=gnu; else STATFMT=none; fi
printf 'CAPS\t@VERSION@\tok\tstat-%s\n' "$STATFMT"
if [ ! -d "$LOGDIR" ]; then
  printf 'ERR\tnodir\t-\n'
  printf 'DONE\t0\t0\n'
  exit 0
fi

tail_ts() {
  # $1 path, $2 size: "<ts|-> <determined> <exact> <trusted>" from a parity-consistent tail parse.
  tb=$TAILB
  while :; do
    if [ "$tb" -ge "$2" ]; then off=0; else off=$(($2 - tb)); fi
    res=$(tail -c +"$((off + 1))" "$1" 2>/dev/null | \
      OFF="$off" RANGELEN="$(($2 - off))" Q0=0 awk "$TAIL_PROG")
    # awk prints "<ts> <consistent> <trusted>"; the timestamp itself holds a space
    trusted=${res##* }; rest=${res% *}; ok=${rest##* }; ts=${rest% *}
    if [ "$off" -eq 0 ]; then printf '%s\t1\t1\t1\n' "$ts"; return 0; fi
    if [ "$ok" = 1 ] && [ "$ts" != "-" ]; then printf '%s\t1\t0\t%s\n' "$ts" "$trusted"; return 0; fi
    if [ "$tb" -ge "$TAILMAX" ]; then printf -- '-\t0\t0\t0\n'; return 0; fi
    tb=$((tb * 2))
  done
}

total=0
skipped=0
OLDIFS=$IFS
# Newest first (ls -t is POSIX); names split on newlines only, no globbing.
IFS='
'
set -f
for name in $(ls -t "$LOGDIR" 2>/dev/null); do
  IFS=$OLDIFS
  case "$name" in *.csv) ;; *) continue ;; esac
  path="$LOGDIR/$name"
  [ -L "$path" ] && { skipped=$((skipped + 1)); continue; }
  [ -f "$path" ] || continue
  case "$name" in
    [A-Za-z0-9]*) ;;
    *) skipped=$((skipped + 1)); continue ;;
  esac
  case "$name" in
    *[!A-Za-z0-9._-]*) skipped=$((skipped + 1)); continue ;;
  esac
  total=$((total + 1))
  [ "$total" -gt "$MAXFILES" ] && continue
  if [ "$STATFMT" = gnu ]; then
    vals=$(stat -c '%s %Y' "$path" 2>/dev/null) || vals=''
    set -- $vals
    size=${1:-0}; mtime=${2:--}
  else
    size=$(wc -c < "$path" 2>/dev/null | tr -d ' '); size=${size:-0}; mtime=-
  fi
  if [ ! -r "$path" ]; then
    printf 'ERR\tunreadable\t%s\n' "$name"
    continue
  fi
  layout=$(head -c "$HEADMAX" "$path" 2>/dev/null | awk "$HEAD_PROG")
  cols=${layout%% *}; sev=${layout#* }
  res=$(tail_ts "$path" "$size")
  printf 'FILE\t%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "$size" "$mtime" "$res" "${cols:--}" "${sev:--}"
done
IFS=$OLDIFS
printf 'DONE\t%s\t%s\n' "$total" "$skipped"
"""

_VERIFY_SCRIPT_TEMPLATE = r"""
LC_ALL=C
export LC_ALL
PATH_=@PATH@
TAILB=@TAILB@
TAIL_PROG=@TAILPROG@
if [ ! -r "$PATH_" ]; then printf 'ERR\tunreadable\n'; exit 0; fi
if stat -c '%s' "$PATH_" >/dev/null 2>&1; then size=$(stat -c '%s' "$PATH_"); else size=$(wc -c < "$PATH_" | tr -d ' '); fi
tb=$TAILB
while :; do
  if [ "$tb" -ge "$size" ]; then off=0; else off=$((size - tb)); fi
  quotes=$(head -c "$off" "$PATH_" | tr -cd '"' | wc -c | tr -d ' ')
  res=$(tail -c +"$((off + 1))" "$PATH_" 2>/dev/null | \
    OFF="$off" RANGELEN="$((size - off))" Q0=$((quotes % 2)) awk "$TAIL_PROG")
  rest=${res% *}; ts=${rest% *}
  if [ "$ts" != "-" ] || [ "$off" -eq 0 ]; then printf 'VERIFIED\t%s\t%s\n' "$ts" "$size"; exit 0; fi
  tb=$((tb * 2))
done
"""


def _fill(template: str, values: dict[str, str]) -> bytes:
    for token, value in values.items():
        template = template.replace(token, value)
    return template.encode("ascii")


def build_probe_script(log_directory: str) -> bytes:
    for program in (_AWK_TAIL, _AWK_HEAD):
        if "'" in program:
            raise ValueError("awk program must not contain single quotes")
    return _fill(
        _PROBE_SCRIPT_TEMPLATE,
        {
            "@LOGDIR@": shlex.quote(log_directory),
            "@MAXFILES@": str(MAX_PROBE_FILES),
            "@HEADMAX@": str(MAX_PROBE_BYTES),
            "@TAILB@": str(TAIL_PROBE_BYTES),
            "@TAILMAX@": str(MAX_PROBE_BYTES),
            "@TAILPROG@": "'" + _AWK_TAIL + "'",
            "@HEADPROG@": "'" + _AWK_HEAD + "'",
            "@VERSION@": PROBE_PROTOCOL_VERSION,
        },
    )


def build_verify_script(path: str) -> bytes:
    return _fill(
        _VERIFY_SCRIPT_TEMPLATE,
        {
            "@PATH@": shlex.quote(path),
            "@TAILB@": str(TAIL_PROBE_BYTES),
            "@TAILPROG@": "'" + _AWK_TAIL + "'",
        },
    )


def parse_probe_output(stdout: bytes) -> ProbeResult:
    """Parse the probe protocol; malformed output discards the whole probe."""
    files: list[ProbedFile] = []
    unreadable: list[str] = []
    total = 0
    skipped = 0
    saw_caps = False
    saw_done = False
    for line in stdout.split(b"\n"):
        if not line:
            continue
        fields = line.split(b"\t")
        kind = fields[0]
        if kind == b"CAPS":
            saw_caps = True
            if len(fields) < 3 or fields[2] != b"ok":
                detail = b"\t".join(fields[2:]).decode("ascii", "replace")
                raise HarvesterUnavailableError(
                    f"host cannot run the log directory probe ({detail or 'degraded'})"
                )
        elif kind == b"FILE":
            if len(fields) != 10:
                raise HarvesterProtocolError("malformed FILE frame")
            name = fields[1].decode("ascii", "replace")
            if not _BASENAME_RE.match(name):
                raise HarvesterProtocolError("unsafe file name in FILE frame")
            last_ts = fields[4].decode("ascii", "replace")
            columns = fields[8].decode("ascii", "replace")
            severity = fields[9].decode("utf-8", "replace")
            files.append(
                ProbedFile(
                    name=name,
                    size=int(fields[2]),
                    mtime=_optional_float(fields[3]),
                    last_ts=None if last_ts == "-" else last_ts,
                    columns=int(columns) if columns.isdigit() else None,
                    severity=None if severity == "-" else severity,
                    determined=fields[5] == b"1",
                    exact=fields[6] == b"1",
                    trusted=fields[7] == b"1",
                )
            )
        elif kind == b"ERR":
            stage = fields[1].decode("ascii", "replace") if len(fields) > 1 else "?"
            if stage == "nodir":
                raise DirectoryUnavailable("log directory does not exist on the SSH target")
            if stage == "unreadable" and len(fields) >= 3:
                unreadable.append(fields[2].decode("ascii", "replace"))
            else:
                raise HarvesterProtocolError(f"unknown ERR stage {stage!r}")
        elif kind == b"DONE":
            saw_done = True
            total = int(fields[1])
            skipped = int(fields[2]) if len(fields) > 2 else 0
        else:
            raise HarvesterProtocolError(
                f"unknown probe frame {kind.decode('ascii', 'replace')!r}"
            )
    if not saw_caps or not saw_done:
        raise HarvesterProtocolError("probe output ended without CAPS/DONE")
    # Skipped names (symlinks, unsafe characters) are not readable candidates.
    unreadable.extend("<skipped>" for _ in range(skipped))
    return ProbeResult(
        files=files,
        unreadable=unreadable,
        total_files=total,
        listing_truncated=total > MAX_PROBE_FILES,
    )


def _optional_float(value: bytes) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


class HarvesterLogDirectoryProbe(LogDirectoryProbe):
    """Remote transport: ephemeral POSIX-sh probe over SSH stdin."""

    def __init__(self, transport: Any) -> None:
        self._transport = transport  # needs run_script_bytes()

    async def _run(self, script: bytes, *, output_limit_bytes: int) -> bytes:
        result = await self._transport.run_script_bytes(
            script, timeout=_PROBE_TIMEOUT_SECONDS, output_limit_bytes=output_limit_bytes
        )
        if result.returncode != 0:
            stderr = result.stderr
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", "replace")
            raise HarvesterProtocolError(
                f"log directory probe exited with {result.returncode}: {stderr[:200]}"
            )
        return result.stdout if isinstance(result.stdout, bytes) else result.stdout.encode()

    async def probe(self, log_directory: str) -> ProbeResult:
        stdout = await self._run(
            build_probe_script(log_directory), output_limit_bytes=MAX_PROBE_FILES * 512
        )
        return parse_probe_output(stdout)

    async def verify_last_ts(self, log_directory: str, name: str) -> tuple[str | None, int]:
        stdout = await self._run(
            build_verify_script(f"{log_directory}/{name}"), output_limit_bytes=4096
        )
        fields = stdout.strip().split(b"\t")
        if fields[0] == b"ERR":
            raise OSError(f"cannot verify {name}")
        if fields[0] != b"VERIFIED" or len(fields) != 3:
            raise HarvesterProtocolError("malformed verification output")
        ts = fields[1].decode("ascii", "replace")
        return (None if ts == "-" else ts), int(fields[2])


# --- discovery verification and window resolution ----------------------------


@dataclass
class DiscoveryState:
    """What verification changed, kept out of the frozen window."""

    files: list[ProbedFile]
    reasons: set[str] = field(default_factory=set)
    verified_name: str | None = None
    verify_bytes: int = 0
    verified_files: int = 0


def _stamp(file: ProbedFile) -> datetime | None:
    return parse_timestamp(file.last_ts) if file.last_ts else None


def _order_key(file: ProbedFile, clock_for: Any) -> tuple[float, str]:
    """Sort key on absolute time when the clock is known.

    After a fall-back transition the wall clock runs backwards: a file whose
    last record says 02:05 CET is newer than one ending at 02:58 CEST. Files
    whose clock is unknown sort by wall-clock time read as UTC.
    """
    stamp = _stamp(file)
    assert stamp is not None
    clock: LogClock = clock_for(file.last_ts)
    absolute = clock.to_absolute(stamp, zone_suffix(file.last_ts)) if clock.known else None
    if absolute is None:
        absolute = stamp.replace(tzinfo=timezone.utc)
    return absolute.timestamp(), file.name


async def _verify(
    probe: LogDirectoryProbe,
    state: DiscoveryState,
    log_directory: str,
    file: ProbedFile,
) -> bool:
    """Replace ``file``'s timestamp with the exact one; False when over budget."""
    if state.verify_bytes + file.size > VERIFY_BUDGET_BYTES:
        return False
    try:
        exact, read_bytes = await probe.verify_last_ts(log_directory, file.name)
    except OSError:
        state.reasons.add(REASON_UNREADABLE)
        state.files = [f for f in state.files if f.name != file.name]
        return True
    state.verify_bytes += read_bytes
    state.verified_files += 1
    state.files = [
        replace(f, last_ts=exact, determined=True, exact=True, trusted=True)
        if f.name == file.name
        else f
        for f in state.files
    ]
    return True


async def verify_discovery(
    probe: LogDirectoryProbe,
    result: ProbeResult,
    *,
    log_directory: str,
    depth_minutes: int,
    clock_for: Any,
) -> DiscoveryState:
    """Establish exact timestamps where a decision depends on them.

    1. The newest file anchors the window: it is re-read with exact quote
       parity from its first byte, repeatedly until the newest verified file
       is at least as new as every unverified one (a planted future date
       cannot move the window).
    2. Files that would be excluded from the window on an unverified,
       untrusted timestamp are verified too, closest to the window first (a
       planted old date cannot hide a file). Past VERIFY_BUDGET_BYTES the
       remaining ones stay excluded and the window is reported incomplete.

    ``clock_for(anchor_ts)`` returns the LogClock used for the window bounds.
    """
    state = DiscoveryState(files=list(result.files))
    verified: set[str] = set()
    while True:
        dated = sorted(
            (f for f in state.files if _stamp(f) is not None),
            key=lambda f: _order_key(f, clock_for),
            reverse=True,
        )
        if not dated or dated[0].name in verified:
            break
        newest = dated[0]
        if not await _verify(probe, state, log_directory, newest):
            state.reasons.add(REASON_DISCOVERY_INCOMPLETE)
            break
        verified.add(newest.name)
        state.verified_name = newest.name
    dated = sorted(
        (f for f in state.files if _stamp(f) is not None),
        key=lambda f: _order_key(f, clock_for),
        reverse=True,
    )
    if not dated:
        return state
    anchor = dated[0]
    bounds = window_bounds(anchor.last_ts or "", depth_minutes, clock_for(anchor.last_ts))
    scan_from = parse_timestamp(bounds.scan_from)
    for file in dated[1:]:  # newest first: the files nearest the window first
        stamp = _stamp(file)
        if stamp is None or scan_from is None or stamp >= scan_from:
            continue  # inside the window: inclusion needs no proof
        if file.exact or file.trusted:
            continue
        if not await _verify(probe, state, log_directory, file):
            state.reasons.add(REASON_DISCOVERY_INCOMPLETE)
            break
    return state


def resolve_directory_window(
    result: ProbeResult,
    *,
    log_directory: str,
    depth_minutes: int,
    state: DiscoveryState | None = None,
    log_timezone: str | None = None,
) -> DirectoryWindow:
    """Anchor the window at the newest complete record; select candidates."""
    files = state.files if state is not None else list(result.files)
    reasons: set[str] = set(state.reasons) if state is not None else set()
    clock_for = lambda anchor_ts: resolve_clock(anchor_ts, log_timezone)  # noqa: E731
    dated = [(f, _stamp(f)) for f in files if _stamp(f) is not None]
    undetermined = [f for f in files if not f.determined and f.size > 0]
    if not files and not result.unreadable:
        raise DirectoryUnavailable(
            f"no csvlog files (*.csv) found in {log_directory}",
            inventory=_inventory(files, result, log_directory, None, None, set(), reasons, None, state),
        )
    if not dated:
        raise DirectoryUnavailable(
            f"no complete csvlog record with a timestamp found in {log_directory}",
            inventory=_inventory(files, result, log_directory, None, None, set(), reasons, None, state),
        )
    dated.sort(key=lambda row: _order_key(row[0], clock_for), reverse=True)
    newest, newest_dt = dated[0]
    anchor_ts = newest.last_ts or ""
    clock = resolve_clock(anchor_ts, log_timezone)
    bounds = window_bounds(anchor_ts, depth_minutes, clock)
    scan_from_dt = parse_timestamp(bounds.scan_from)
    formats = {
        f.name: fmt
        for f in files
        for fmt in (csv_format_from_columns(f.columns, f.severity),)
        if fmt is not None
    }
    csv_format = formats.get(newest.name) or next(
        (formats[f.name] for f, _ in dated if f.name in formats), None
    )
    in_window = {f.name for f, stamp in dated if scan_from_dt is None or stamp >= scan_from_dt}
    in_window.update(f.name for f in undetermined)
    if csv_format is None:
        raise DirectoryUnavailable(
            "cannot detect the csvlog layout: no file starts with a complete 23, 24, or "
            "26 column PostgreSQL csvlog record",
            inventory=_inventory(
                files, result, log_directory, newest, bounds, in_window, reasons, clock, state
            ),
        )
    # Undetermined files (probe cap reached before a consistent parse) may
    # hold records newer than the anchor: scan them fully, and say so.
    if undetermined:
        reasons.add(REASON_DISCOVERY_INCOMPLETE)
    if result.unreadable:
        reasons.add(REASON_UNREADABLE)
    if result.listing_truncated:
        reasons.add(REASON_CANDIDATE_LIMIT)
    candidates = [
        LogFileInfo(name=f.name, size=f.size, modification=newest_dt) for f in undetermined
    ] + [
        LogFileInfo(name=f.name, size=f.size, modification=stamp)
        for f, stamp in dated
        if f.name in in_window
    ]
    if len(candidates) > MAX_CANDIDATE_FILES:
        reasons.add(REASON_CANDIDATE_LIMIT)
        candidates = candidates[:MAX_CANDIDATE_FILES]
    locale_supported = all(
        formats.get(f.name, csv_format).locale_supported for f in files if f.name in in_window
    )
    inventory = _inventory(
        files, result, log_directory, newest, bounds, in_window, reasons, clock, state
    )
    return DirectoryWindow(
        bounds=bounds,
        clock=clock,
        anchor_ts=anchor_ts,
        candidates=tuple(candidates),
        csv_format=csv_format,
        file_versions={name: fmt.server_version_num for name, fmt in formats.items()},
        locale_supported=locale_supported,
        files_unreadable=len(result.unreadable),
        truncation_reasons=frozenset(reasons),
        inventory=inventory,
    )


def _inventory(
    files: list[ProbedFile],
    result: ProbeResult,
    log_directory: str,
    newest: ProbedFile | None,
    bounds: WindowBounds | None,
    in_window: set[str],
    reasons: set[str],
    clock: LogClock | None,
    state: DiscoveryState | None,
) -> dict[str, Any]:
    """Shape-compatible with the pg_ls_logdir inventory (log_files_overview).

    Nothing here is server state: ``is_current`` stays False because the
    active file is unknown, ``block_size`` and the rotation settings are None.
    """
    def _row_key(f: ProbedFile) -> tuple[float, str]:
        stamp = _stamp(f)
        if stamp is None:
            return (float("-inf"), f.name)
        absolute = clock.to_absolute(stamp, zone_suffix(f.last_ts)) if clock and clock.known else None
        if absolute is None:
            absolute = stamp.replace(tzinfo=timezone.utc)
        return (absolute.timestamp(), f.name)

    rows = []
    for f in sorted(files, key=_row_key, reverse=True):
        stamp = _stamp(f)
        rows.append(
            {
                "name": f.name,
                "size_bytes": int(f.size),
                "modification": stamp.strftime("%Y-%m-%d %H:%M:%S") if stamp else None,
                "in_window": f.name in in_window,
                "is_current": False,
                "is_newest": newest is not None and f.name == newest.name,
                "last_record_known": bool(f.determined),
                "last_record_exact": bool(f.exact or f.trusted),
                "csv_columns": f.columns,
            }
        )
    csv_format = csv_format_from_columns(newest.columns, newest.severity) if newest else None
    offset = None
    if clock is not None and newest is not None and newest.last_ts:
        anchor = parse_timestamp(newest.last_ts)
        if anchor is not None:
            offset = clock.offset_for(anchor, zone_suffix(newest.last_ts))
    return {
        "files": rows,
        "file_count_total": int(result.total_files),
        "total_bytes": int(sum(f.size for f in files)),
        "window_from": bounds.window_from if bounds else None,
        "collected_to": bounds.window_to if bounds else None,
        "settings": {
            "logging_collector": "unknown",
            "log_destination": "csvlog",
            "log_directory": log_directory,
            "log_filename": "unknown",
            "log_timezone": clock.label if clock is not None else "unknown",
            "log_utc_offset_seconds": offset,
            "block_size": None,
            "log_rotation_age": "unknown",
            "log_rotation_size": "unknown",
            "log_truncate_on_rotation": "unknown",
        },
        "source": {
            "kind": "directory",
            "log_directory": log_directory,
            "files_probed": len(files),
            "files_undetermined": sum(1 for f in files if not f.determined and f.size > 0),
            "files_unreadable": len(result.unreadable),
            "files_verified": state.verified_files if state is not None else 0,
            "listing_truncated": bool(result.listing_truncated),
            "anchor_verified": bool(
                state is not None and newest is not None and state.verified_name == newest.name
            ),
            "discovery_reasons": sorted(reasons),
            "csv_format": (
                {
                    "columns": csv_format.columns,
                    "server_version_num": csv_format.server_version_num,
                    "label": csv_format.label,
                }
                if csv_format is not None
                else None
            ),
            "window_anchor": "newest complete record timestamp",
            "window_scan_from": bounds.scan_from if bounds else None,
            "window_scan_to": bounds.scan_to if bounds else None,
        },
    }


def resolve_log_timezone(name: str) -> ZoneInfo:
    """Validate an IANA zone name for --log-timezone."""
    return ZoneInfo(name)


def resolve_clock(anchor_ts: str | None, log_timezone: str | None) -> LogClock:
    """The log clock for a window anchored at ``anchor_ts``.

    An explicit IANA zone wins and resolves every record (DST included).
    Numeric suffixes (``+03``, ``-0530``) and UTC aliases are exact fixed
    offsets; a named abbreviation is ambiguous, so the offset stays unknown and
    chart items say so instead of presenting the log clock as UTC.
    """
    if log_timezone:
        return LogClock(label=log_timezone, zone=ZoneInfo(log_timezone))
    suffix = zone_suffix(anchor_ts)
    if not suffix:
        return LogClock(label="unknown")
    if suffix in _UTC_LABELS:
        return LogClock(label="UTC", fixed_offset=0)
    if _NUMERIC_TZ_RE.match(suffix):
        sign = -1 if suffix[0] == "-" else 1
        digits = suffix[1:].replace(":", "")
        hours = int(digits[:2])
        minutes = int(digits[2:4]) if len(digits) >= 4 else 0
        return LogClock(label=suffix, fixed_offset=sign * (hours * 3600 + minutes * 60))
    return LogClock(label=suffix)
