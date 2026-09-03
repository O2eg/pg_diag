"""Remote bash harvester (plan §15, revision 3.2).

One ephemeral POSIX-sh script per phase, sent over SSH stdin (nothing is
installed on the host): it verifies tool capabilities, binary-searches the
window boundary, streams each file range through a single awk program that
applies the recall filter, an identity-aware physically-adjacent RLE, the
window bounds, and a hard wire budget, and emits a line-framed protocol with
length-prefixed raw records. The collector parses that protocol back into the
same :class:`ScanResult` the local source produces.
"""

from __future__ import annotations

import re
import shlex
from typing import Any

from .model import (
    PHASE_WALLCLOCK_SECONDS,
    REASON_RETURN_LIMIT,
    REASON_ROTATION_RACE,
    REASON_SCAN_LIMIT,
    REASON_TIME_LIMIT,
    REASON_UNREADABLE,
    RawSeries,
    ScanRequest,
    ScanResult,
    ScanStats,
)
from .recall import to_awk_condition
from .sources import LogScanSource

PROTOCOL_VERSION = "v1"
_BASENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.csv$")
_HARVEST_TIMEOUT_SECONDS = PHASE_WALLCLOCK_SECONDS - 5.0
_HOST_TIME_BUDGET_SECONDS = int(PHASE_WALLCLOCK_SECONDS * 0.85)


class HarvesterUnavailableError(Exception):
    """The host cannot run the harvester (missing tools, degraded CAPS)."""


class HarvesterProtocolError(Exception):
    """The harvester output is incomplete or malformed; discard the result."""


# The awk program must stay single-quote-free: it is embedded into the shell
# script inside single quotes. Semantics mirror rle.PhysicalRle and
# LocalLogSource._scan_range and are pinned by cross-equivalence tests.
_AWK_PROGRAM = r"""
BEGIN {
  wfrom = substr(ENVIRON["WFROM"], 1, 19)
  wto = substr(ENVIRON["WTO"], 1, 19)
  rawcap = ENVIRON["RAWCAP"] + 0
  wireleft = ENVIRON["WIRELEFT"] + 0
  rangelen = ENVIRON["RANGELEN"] + 0
  skipfirst = ENVIRON["SKIPFIRST"] + 0
  fname = ENVIRON["FNAME"]
  cum = 0; have_prev = 0; cnt = 0; spent = 0
  rec_active = 0; rec_q = 0; rec_match = 0
  matched = 0; dropped = 0; budget_hit = 0
}
{
  cum += length($0) + 1
  if (NR == 1 && skipfirst) { dropped += 1; next }
  if (have_prev) processline(prev_line, prev_nr)
  prev_line = $0; prev_nr = NR; have_prev = 1
}
END {
  if (have_prev) {
    if (cum == rangelen) processline(prev_line, prev_nr)
    else dropped += 1
  }
  if (rec_active) {
    if (rec_match) dropped += 1
    resetrecord()
  }
  flushrun()
  printf "META\t%s\t%d\t%d\t%d\t%d\n", fname, NR, matched, dropped, budget_hit
  printf "SPENT=%d\n", spent | "cat 1>&2"
  close("cat 1>&2")
  if (budget_hit) exit 3
}
function processline(l, n,   c) {
  if (!rec_active) {
    if (l !~ /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] /) {
      if (__RECALL__) dropped += 1
      return
    }
    c = index(l, ",")
    if (c <= 1) {
      if (__RECALL__) dropped += 1
      return
    }
    rec_active = 1
    rec_match = (__RECALL__) ? 1 : 0
    rec_first_n = n; rec_last_n = n
    rec_ts = substr(l, 1, c - 1)
    rec_raw = ""; rec_len = 0; rec_q = 0
    appendrecord(l, 0)
  } else {
    rec_last_n = n
    appendrecord(l, 1)
  }
  if (!rec_q) finishrecord()
}
function appendrecord(l, separator,   left) {
  if (separator) {
    rec_len += 1
    if (rec_match && length(rec_raw) < rawcap) rec_raw = rec_raw "\n"
  }
  rec_len += length(l)
  if (rec_match && length(rec_raw) < rawcap) {
    left = rawcap - length(rec_raw)
    rec_raw = rec_raw substr(l, 1, left)
  }
  rec_q = quotestate(l, rec_q)
}
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
function finishrecord(   stamp, rtrunc) {
  if (rec_match) {
    stamp = substr(rec_ts, 1, 19)
    if (stamp >= wfrom && stamp <= wto) {
      matched += 1
      rtrunc = (rec_len > rawcap) ? 1 : 0
      processrecord(rec_raw, rec_first_n, rec_last_n, rec_ts, rtrunc)
    }
  }
  resetrecord()
}
function resetrecord() {
  rec_active = 0; rec_q = 0; rec_match = 0
  rec_first_n = 0; rec_last_n = 0; rec_ts = ""
  rec_raw = ""; rec_len = 0
}
function processrecord(l, firstn, lastn, ts, truncated,   id, tl, no_merge) {
  no_merge = truncated || index(l, " ms  plan:") > 0
  if (splitkey(l) && !no_merge) { id = SK_ID; tl = SK_TAIL }
  else { id = "\001unparsed"; tl = firstn "" }
  if (cnt && id == cur_id && tl == cur_tl && firstn == last_n + 1) {
    cnt += 1; last_n = lastn; last_ts = ts
    return
  }
  flushrun()
  cur_id = id; cur_tl = tl; cnt = 1
  first_n = firstn; last_n = lastn; first_ts = ts; last_ts = ts
  raw = l
  rtrunc = truncated ? 1 : 0
}
function flushrun(   header, cost) {
  if (!cnt) return
  header = sprintf("RUN\t%d\t%d\t%d\t%s\t%s\t%d\t%d", \
                   first_n, last_n, cnt, first_ts, last_ts, length(raw), rtrunc)
  cost = length(header) + 2 + length(raw)
  if (spent + cost > wireleft) { budget_hit = 1; cnt = 0; return }
  print header
  printf "%s\n", raw
  spent += cost
  cnt = 0
}
function splitkey(l,   i, ch, q, commas, fs, idp, len) {
  len = length(l); q = 0; commas = 0; fs = 1; idp = ""
  for (i = 1; i <= len; i++) {
    ch = substr(l, i, 1)
    if (q) {
      if (ch == "\"") {
        if (substr(l, i + 1, 1) == "\"") { i++; continue }
        q = 0
      }
      continue
    }
    if (ch == "\"") { q = 1; continue }
    if (ch != ",") continue
    if (commas >= 1 && commas <= 4) idp = idp substr(l, fs, i - fs) ","
    commas += 1
    fs = i + 1
    if (commas == 11) { SK_ID = idp; SK_TAIL = substr(l, i + 1); return 1 }
  }
  return 0
}
"""

_SCRIPT_TEMPLATE = r"""
LC_ALL=C
export LC_ALL
LOGDIR=@LOGDIR@
WFROM=@WFROM@
WTO=@WTO@
RAWCAP=@RAWCAP@
SCAN_LEFT=@SCANBUDGET@
WIRE_LEFT=@WIREBUDGET@
# Frame overhead reserve: CAPS/DONE plus per-file FILE/META/FILE_END frames are
# part of the wire budget too (review finding); constants are upper bounds.
WIRE_LEFT=$((WIRE_LEFT - 1024))
TIME_S=@TIMEBUDGET@
AWK_PROG=@AWKPROG@
STOP=0
SCANNED=0
REASONS=""
start_epoch=$(date +%s 2>/dev/null || echo 0)

for tool in awk tail head sed cut sort date; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    printf 'CAPS\t@VERSION@\tdegraded\tmissing-%s\n' "$tool"
    printf 'DONE\t0\tdegraded\n'
    exit 0
  fi
done
if stat -c '%s %d %i' "$LOGDIR" >/dev/null 2>&1; then STATFMT=gnu; else STATFMT=none; fi
printf 'CAPS\t@VERSION@\tok\tstat-%s\n' "$STATFMT"
exec 3>&1

probe_ts() {
  tail -c +"$(($2 + 1))" "$1" 2>/dev/null | head -c 65536 | \
    OFFSET="$2" awk 'BEGIN { pos = 0; off = ENVIRON["OFFSET"] + 0 }
      { len = length($0) + 1
        if (NR == 1 && off > 0) { pos += len; next }
        if ($0 ~ /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] /) {
          c = index($0, ",")
          if (c > 1) { printf "%s\t%d\n", substr($0, 1, c - 1), off + pos; exit }
        }
        pos += len }'
}

ts_lt() {
  [ "$1" = "$2" ] && return 1
  [ "$(printf '%s\n%s\n' "$1" "$2" | sort | head -n 1)" = "$1" ]
}

find_start() {
  f=$1; size=$2; lo=0; hi=$size
  while [ $((hi - lo)) -gt 16384 ]; do
    mid=$(((lo + hi) / 2))
    res=$(probe_ts "$f" "$mid")
    [ -z "$res" ] && break
    stamp=$(printf '%.19s' "$(printf '%s' "$res" | cut -f1)")
    if ts_lt "$stamp" "$(printf '%.19s' "$WFROM")"; then lo=$mid; else hi=$mid; fi
  done
  res=$(probe_ts "$f" "$lo")
  if [ -n "$res" ]; then printf '%s\n' "$(printf '%s' "$res" | cut -f2)"; else printf '0\n'; fi
}

scan_file() {
  [ "$STOP" = 1 ] && return 0
  now=$(date +%s 2>/dev/null || echo 0)
  if [ "$now" -gt 0 ] && [ "$start_epoch" -gt 0 ] && \
     [ $((now - start_epoch)) -ge "$TIME_S" ]; then
    REASONS="$REASONS time_limit_hit"; STOP=1; return 0
  fi
  name=$1; msize=$2; boundary=$3
  path="$LOGDIR/$name"
  if [ -L "$path" ]; then printf 'ERR\tsymlink\t%s\t-\n' "$name"; return 0; fi
  if [ ! -f "$path" ]; then printf 'ERR\tvanished\t%s\t-\n' "$name"; return 0; fi
  if [ "$STATFMT" = gnu ]; then
    vals=$(stat -c '%s %d %i' "$path" 2>/dev/null) || vals=''
    set -- $vals
    size=${1:-$msize}; dev=${2:-0}; ino=${3:-0}
  else
    size=$msize; dev=0; ino=0
  fi
  printf 'FILE\t%s\t%s\t%s\t%s\n' "$name" "$size" "$dev" "$ino"
  start=0
  aligned=1
  if [ "$boundary" = 1 ] && [ "$size" -gt 0 ]; then start=$(find_start "$path" "$size"); fi
  if [ "$SCAN_LEFT" -le 0 ]; then REASONS="$REASONS scan_limit_hit"; STOP=1; return 0; fi
  WIRE_LEFT=$((WIRE_LEFT - 512))
  if [ "$WIRE_LEFT" -le 0 ]; then REASONS="$REASONS return_limit_hit"; STOP=1; return 0; fi
  range=$((size - start))
  if [ "$range" -gt "$SCAN_LEFT" ]; then
    res=$(probe_ts "$path" $((size - SCAN_LEFT)))
    if [ -n "$res" ]; then start=$(printf '%s' "$res" | cut -f2)
    else start=$((size - SCAN_LEFT)); aligned=0; fi
    range=$((size - start))
    REASONS="$REASONS scan_limit_hit"
  fi
  if [ "$range" -le 0 ]; then
    printf 'META\t%s\t0\t0\t0\t0\n' "$name"
    printf 'FILE_END\t%s\t%s\t%s\t%s\n' "$name" "$dev" "$ino" "$size"
    return 0
  fi
  skipfirst=0
  if [ "$start" -gt 0 ] && [ "$aligned" = 0 ]; then skipfirst=1; fi
  captured=$( { { tail -c +"$((start + 1))" "$path" 2>/dev/null || \
      printf 'TAILRC=%s\n' "$?" 1>&2; } | head -c "$range" | \
    FNAME="$name" RANGELEN="$range" SKIPFIRST="$skipfirst" WIRELEFT="$WIRE_LEFT" \
    RAWCAP="$RAWCAP" WFROM="$WFROM" WTO="$WTO" awk "$AWK_PROG" 1>&3; } 2>&1 )
  rc=$?
  SCAN_LEFT=$((SCAN_LEFT - range))
  SCANNED=$((SCANNED + range))
  spent=$(printf '%s\n' "$captured" | sed -n 's/^SPENT=//p' | tail -n 1)
  case "$spent" in ''|*[!0-9]*) spent=0 ;; esac
  WIRE_LEFT=$((WIRE_LEFT - spent))
  tailrc=$(printf '%s\n' "$captured" | sed -n 's/^TAILRC=//p' | tail -n 1)
  if [ -n "$tailrc" ] && [ "$tailrc" != 141 ]; then
    # The producer failed (permissions, I/O error): rc of the pipeline is the
    # awk status only, so this side-channel is the ONLY read-success signal.
    printf 'ERR\tproducer\t%s\trc%s\n' "$name" "$tailrc"
  fi
  if [ "$rc" = 3 ]; then REASONS="$REASONS return_limit_hit"; STOP=1
  elif [ "$rc" != 0 ]; then printf 'ERR\tread\t%s\trc%s\n' "$name" "$rc"; fi
  if [ "$STATFMT" = gnu ]; then
    vals=$(stat -c '%s %d %i' "$path" 2>/dev/null) || vals=''
    set -- $vals
    printf 'FILE_END\t%s\t%s\t%s\t%s\n' "$name" "${2:-0}" "${3:-0}" "${1:-0}"
  else
    printf 'FILE_END\t%s\t0\t0\t%s\n' "$name" "$size"
  fi
}

@SCANCALLS@
printf 'DONE\t%s\t%s\n' "$SCANNED" "${REASONS:--}"
"""


def build_script(request: ScanRequest, *, stats: ScanStats) -> bytes:
    """Generate the per-run harvester; invalid basenames are rejected here."""
    calls = []
    valid: list[Any] = []
    for info in request.files:
        if not _BASENAME_RE.match(info.name):
            stats.files_unreadable += 1
            stats.truncation_reasons.add(REASON_UNREADABLE)
            continue
        valid.append(info)
    for index, info in enumerate(valid):
        boundary = "1" if index == len(valid) - 1 else "0"
        calls.append(f"scan_file {shlex.quote(info.name)} {int(info.size)} {boundary}")
    awk_program = _AWK_PROGRAM.replace(
        "__RECALL__", to_awk_condition(request.recall_clauses, variable="l")
    )
    if "'" in awk_program:
        raise ValueError("awk program must not contain single quotes")
    script = _SCRIPT_TEMPLATE
    for token, value in {
        "@LOGDIR@": shlex.quote(request.log_directory),
        "@WFROM@": shlex.quote(request.window_from_ts),
        "@WTO@": shlex.quote(request.window_to_ts),
        "@RAWCAP@": str(int(request.raw_record_cap)),
        "@SCANBUDGET@": str(int(request.scan_budget_bytes)),
        "@WIREBUDGET@": str(int(request.wire_budget_bytes)),
        "@TIMEBUDGET@": str(_HOST_TIME_BUDGET_SECONDS),
        "@AWKPROG@": "'" + awk_program + "'",
        "@VERSION@": PROTOCOL_VERSION,
        "@SCANCALLS@": "\n".join(calls),
    }.items():
        script = script.replace(token, value)
    return script.encode("ascii")


def parse_output(stdout: bytes, *, stats: ScanStats) -> ScanResult:
    """Parse the harvester protocol; any malformation discards the result.

    Frames are committed per file: RUN/META stay staged until FILE_END proves
    the read succeeded (no producer error, identity unchanged, no truncation).
    A failed file contributes nothing except an honest incompleteness reason.
    """
    series: list[RawSeries] = []
    current_file: str | None = None
    staged: list[RawSeries] = []
    staged_matched = 0
    staged_dropped = 0
    staged_budget_hit = False
    file_before: tuple[int, int, int] | None = None
    file_failed: str | None = None
    saw_caps = False
    saw_done = False
    position = 0
    length = len(stdout)

    def _commit(after: tuple[int, int, int] | None) -> None:
        nonlocal staged, staged_matched, staged_dropped, staged_budget_hit
        nonlocal file_before, file_failed, current_file
        if file_failed is not None:
            if file_failed == "vanished":
                stats.files_vanished += 1
                stats.truncation_reasons.add(REASON_ROTATION_RACE)
            else:
                stats.files_unreadable += 1
                stats.truncation_reasons.add(REASON_UNREADABLE)
        else:
            identity_ok = True
            if file_before is not None and after is not None:
                before_dev, before_ino, before_size = file_before
                after_dev, after_ino, after_size = after
                if (before_dev, before_ino) != (0, 0) and (
                    (before_dev, before_ino) != (after_dev, after_ino) or after_size < before_size
                ):
                    identity_ok = False
            if identity_ok:
                series.extend(staged)
                stats.files_read += 1
                stats.matched_lines += staged_matched
                stats.dropped_lines += staged_dropped
                if staged_budget_hit:
                    stats.truncation_reasons.add(REASON_RETURN_LIMIT)
            else:
                # Rotation reused the basename or the file was truncated:
                # the plan requires discarding everything read from it.
                stats.truncation_reasons.add(REASON_ROTATION_RACE)
                stats.files_vanished += 1
        staged = []
        staged_matched = 0
        staged_dropped = 0
        staged_budget_hit = False
        file_before = None
        file_failed = None
        current_file = None

    while position < length:
        newline = stdout.find(b"\n", position)
        if newline < 0:
            raise HarvesterProtocolError("unterminated frame at end of output")
        line = stdout[position:newline]
        position = newline + 1
        fields = line.split(b"\t")
        kind = fields[0]
        if kind == b"CAPS":
            saw_caps = True
            if len(fields) < 3 or fields[2] != b"ok":
                detail = b"\t".join(fields[2:]).decode("ascii", "replace")
                raise HarvesterUnavailableError(
                    f"host cannot run the log harvester ({detail or 'degraded'})"
                )
        elif kind == b"FILE":
            current_file = fields[1].decode("ascii", "replace")
            file_before = (int(fields[3]), int(fields[4]), int(fields[2]))
        elif kind == b"FILE_END":
            after = (int(fields[2]), int(fields[3]), int(fields[4]))
            _commit(after)
        elif kind == b"RUN":
            if current_file is None:
                raise HarvesterProtocolError("RUN frame outside of a FILE block")
            raw_len = int(fields[6])
            raw = stdout[position : position + raw_len]
            end_byte = stdout[position + raw_len : position + raw_len + 1]
            if len(raw) != raw_len or end_byte != b"\n":
                raise HarvesterProtocolError("RUN payload does not match its length prefix")
            position += raw_len + 1
            staged.append(
                RawSeries(
                    file=current_file,
                    first_lineno=int(fields[1]),
                    last_lineno=int(fields[2]),
                    count=int(fields[3]),
                    first_ts=fields[4].decode("ascii", "replace"),
                    last_ts=fields[5].decode("ascii", "replace"),
                    raw_record=raw,
                    raw_truncated=fields[7] == b"1",
                )
            )
        elif kind == b"META":
            if current_file is None:
                raise HarvesterProtocolError("META frame outside of a FILE block")
            staged_matched += int(fields[3])
            staged_dropped += int(fields[4])
            staged_budget_hit = fields[5] == b"1"
        elif kind == b"ERR":
            stage = fields[1].decode("ascii", "replace")
            if current_file is None:
                # vanished / symlink: rejected before FILE was ever printed
                if stage == "vanished":
                    stats.files_vanished += 1
                    stats.truncation_reasons.add(REASON_ROTATION_RACE)
                else:
                    stats.files_unreadable += 1
                    stats.truncation_reasons.add(REASON_UNREADABLE)
            else:
                file_failed = stage
        elif kind == b"DONE":
            if current_file is not None:
                raise HarvesterProtocolError("DONE before the last FILE_END")
            saw_done = True
            stats.scanned_bytes += int(fields[1])
            reasons = fields[2].decode("ascii", "replace")
            for reason in reasons.split():
                if reason in (
                    REASON_SCAN_LIMIT,
                    REASON_RETURN_LIMIT,
                    REASON_TIME_LIMIT,
                ):
                    stats.truncation_reasons.add(reason)
        else:
            raise HarvesterProtocolError(f"unknown frame {kind.decode('ascii', 'replace')!r}")
    if not saw_caps or not saw_done:
        raise HarvesterProtocolError("harvester output ended without CAPS/DONE")
    return ScanResult(
        series=series,
        stats=stats,
        covered_from_ts=min((s.first_ts for s in series), default=None),
        covered_to_ts=max((s.last_ts for s in series), default=None),
    )


class BashHarvesterSource(LogScanSource):
    """Remote transport: ephemeral POSIX-sh harvester over SSH stdin."""

    def __init__(self, transport: Any) -> None:
        self._transport = transport  # needs run_script_bytes()

    async def scan(self, request: ScanRequest) -> ScanResult:
        stats = ScanStats(files_seen=len(request.files))
        script = build_script(request, stats=stats)
        result = await self._transport.run_script_bytes(script, timeout=_HARVEST_TIMEOUT_SECONDS)
        if result.returncode != 0:
            stderr = result.stderr
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", "replace")
            raise HarvesterProtocolError(
                f"harvester exited with {result.returncode}: {stderr[:200]}"
            )
        stdout = result.stdout if isinstance(result.stdout, bytes) else result.stdout.encode()
        return parse_output(stdout, stats=stats)
