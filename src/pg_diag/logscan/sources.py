"""Log scan sources (plan §15.1).

Core build ships :class:`LocalLogSource` (pg_diag installed on the database
host — pure Python, no shell, no PostgreSQL backend involvement). The bash
harvester (remote) plugs into the same :class:`LogScanSource` interface.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import BinaryIO

from . import recall
from .model import (
    MAX_PROBE_DOUBLINGS,
    PROBE_BYTES,
    REASON_NON_MONOTONIC,
    REASON_RETURN_LIMIT,
    REASON_ROTATION_RACE,
    REASON_SCAN_LIMIT,
    REASON_TIME_LIMIT,
    REASON_UNREADABLE,
    ScanRequest,
    ScanResult,
    ScanStats,
)
from .rle import PhysicalRle, ts_prefix

_TS_COMPARE_LEN = 19  # YYYY-MM-DD HH:MM:SS
_SERIES_WIRE_OVERHEAD = 64
_QUOTE = 0x22


class _LogicalRecordAssembler:
    """Assemble newline-containing PostgreSQL CSV records with a hard cap."""

    def __init__(self, raw_record_cap: int) -> None:
        self._cap = raw_record_cap
        self.active = False
        self.matched = False
        self.in_quotes = False
        self.first_lineno = 0
        self.last_lineno = 0
        self.raw = bytearray()
        self.raw_length = 0

    def start(self, lineno: int, line: bytes, *, matched: bool) -> None:
        self.active = True
        self.matched = matched
        self.in_quotes = False
        self.first_lineno = self.last_lineno = lineno
        self.raw.clear()
        self.raw_length = 0
        self._append(line, separator=False)

    def continuation(self, lineno: int, line: bytes) -> None:
        self.last_lineno = lineno
        self._append(line, separator=True)

    def take(self) -> tuple[int, int, bytes, bool, bool]:
        result = (
            self.first_lineno,
            self.last_lineno,
            bytes(self.raw),
            self.raw_length > self._cap,
            self.matched,
        )
        self.active = False
        self.matched = False
        self.in_quotes = False
        self.raw.clear()
        self.raw_length = 0
        return result

    def discard(self) -> bool:
        matched = self.matched
        self.active = False
        self.matched = False
        self.in_quotes = False
        self.raw.clear()
        self.raw_length = 0
        return matched

    def _append(self, line: bytes, *, separator: bool) -> None:
        if separator:
            self.raw_length += 1
            if len(self.raw) < self._cap:
                self.raw.extend(b"\n"[: self._cap - len(self.raw)])
        self.raw_length += len(line)
        if len(self.raw) < self._cap:
            self.raw.extend(line[: self._cap - len(self.raw)])
        self.in_quotes = _quote_state(line, self.in_quotes)


def _quote_state(line: bytes, in_quotes: bool) -> bool:
    index = 0
    while index < len(line):
        if line[index] != _QUOTE:
            index += 1
            continue
        if in_quotes and index + 1 < len(line) and line[index + 1] == _QUOTE:
            index += 2
            continue
        in_quotes = not in_quotes
        index += 1
    return in_quotes


class LogScanSource:
    """One report-level scan of the log window."""

    async def scan(self, request: ScanRequest) -> ScanResult:
        raise NotImplementedError


def _looks_like_ts(value: str) -> bool:
    return (
        len(value) >= _TS_COMPARE_LEN
        and value[:4].isdigit()
        and value[4] == "-"
        and value[7] == "-"
        and value[10] == " "
    )


def _first_ts_at(handle: BinaryIO, offset: int, size: int) -> tuple[str | None, int]:
    """First complete-line timestamp at/after ``offset``; (ts, line_offset)."""
    probe = PROBE_BYTES
    for _ in range(MAX_PROBE_DOUBLINGS):
        handle.seek(offset)
        data = handle.read(min(probe, size - offset))
        start = 0
        if offset > 0:
            newline = data.find(b"\n")
            if newline < 0:
                probe *= 2
                continue
            start = newline + 1
        position = start
        while position < len(data):
            end = data.find(b"\n", position)
            if end < 0:
                break
            ts = ts_prefix(data[position:end])
            if _looks_like_ts(ts):
                return ts, offset + position
            position = end + 1
        probe *= 2
    return None, offset


def _find_window_start(
    handle: BinaryIO,
    size: int,
    window_from_ts: str,
    stats: ScanStats,
) -> int:
    """Binary search the byte offset of the window boundary (plan §4/§15.4)."""
    boundary = window_from_ts[:_TS_COMPARE_LEN]
    low, high = 0, size
    while high - low > PROBE_BYTES:
        mid = (low + high) // 2
        ts, _ = _first_ts_at(handle, mid, size)
        if ts is None:
            # Long multiline record or unparsable region: fall back to a
            # conservative bound; the tail-biased budget keeps this cheap.
            break
        if ts[:_TS_COMPARE_LEN] < boundary:
            low = mid
        else:
            high = mid
    start = low
    ts, aligned = _first_ts_at(handle, start, size)
    if ts is not None and start > 0:
        before_ts, _ = _first_ts_at(handle, max(0, start - PROBE_BYTES), size)
        if before_ts is not None and before_ts[:_TS_COMPARE_LEN] > ts[:_TS_COMPARE_LEN]:
            stats.truncation_reasons.add(REASON_NON_MONOTONIC)
    return aligned if ts is not None else 0


class LocalLogSource(LogScanSource):
    """Direct file reading when pg_diag runs on the database host."""

    def __init__(self, log_directory: str, *, chunk_bytes: int = 1 << 20) -> None:
        self._log_directory = log_directory
        self._chunk_bytes = chunk_bytes

    async def scan(self, request: ScanRequest) -> ScanResult:
        # Blocking file I/O must not run on the event loop (slow disk / NFS
        # would defeat the phase timeout) — review finding, 2026-08-31.
        return await asyncio.to_thread(self._scan_sync, request)

    # -- synchronous implementation (worker thread) --

    def _scan_sync(self, request: ScanRequest) -> ScanResult:
        stats = ScanStats(files_seen=len(request.files))
        series: list = []
        wire_used = 0
        stop = False
        base_real = os.path.realpath(self._log_directory)
        # Newest files first: on budget exhaustion the old edge is sacrificed.
        for index, info in enumerate(request.files):
            if stop:
                break
            if self._deadline_hit(request, stats):
                break
            is_boundary_file = index == len(request.files) - 1
            handle = self._open_candidate(info.name, base_real, stats)
            if handle is None:
                continue
            staged: list = []
            try:
                opened_stat = os.fstat(handle.fileno())
                size = opened_stat.st_size
                start = 0
                if is_boundary_file and size > 0:
                    start = _find_window_start(handle, size, request.window_from_ts, stats)
                remaining_scan = request.scan_budget_bytes - stats.scanned_bytes
                if remaining_scan <= 0:
                    stats.truncation_reasons.add(REASON_SCAN_LIMIT)
                    break
                if size - start > remaining_scan:
                    # Tail-biased truncation: keep the newest part of the range.
                    ts, aligned = _first_ts_at(handle, size - remaining_scan, size)
                    start = aligned if ts is not None else size - remaining_scan
                    stats.truncation_reasons.add(REASON_SCAN_LIMIT)
                try:
                    wire_used, stop = self._scan_range(
                        handle, info.name, start, size, request, stats, staged, wire_used
                    )
                except OSError:
                    # Mid-read failure: nothing from this file may be trusted.
                    stats.files_unreadable += 1
                    stats.truncation_reasons.add(REASON_UNREADABLE)
                    continue
                if self._identity_intact(info.name, opened_stat, size, stats):
                    series.extend(staged)  # commit only after a proven-clean read
                    stats.files_read += 1
            finally:
                handle.close()
        return ScanResult(
            series=series,
            stats=stats,
            covered_from_ts=min((s.first_ts for s in series), default=None),
            covered_to_ts=max((s.last_ts for s in series), default=None),
        )

    def _open_candidate(self, name: str, base_real: str, stats: ScanStats):
        """Open one candidate with basename validation and path containment."""
        if (
            os.sep in name
            or (os.altsep and os.altsep in name)
            or name in (".", "..")
            or not name.endswith(".csv")
        ):
            stats.files_unreadable += 1
            stats.truncation_reasons.add(REASON_UNREADABLE)
            return None
        path = os.path.join(self._log_directory, name)
        real = os.path.realpath(path)
        if real != os.path.join(base_real, name):
            # Symlink pointing outside (or renamed on the fly): refuse to read.
            stats.files_unreadable += 1
            stats.truncation_reasons.add(REASON_UNREADABLE)
            return None
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            return os.fdopen(os.open(path, flags), "rb")
        except FileNotFoundError:
            stats.files_vanished += 1
            stats.truncation_reasons.add(REASON_ROTATION_RACE)
            return None
        except OSError:
            stats.files_unreadable += 1
            stats.truncation_reasons.add(REASON_UNREADABLE)
            return None

    def _identity_intact(
        self,
        name: str,
        opened_stat: os.stat_result,
        size_at_open: int,
        stats: ScanStats,
    ) -> bool:
        """Rotation reusing the basename, or truncation, between open and end.

        On any doubt the file's staged series are discarded (plan §15.8): a
        replaced or truncated file cannot vouch for what was read from it.
        """
        try:
            after = os.lstat(os.path.join(self._log_directory, name))
        except OSError:
            stats.files_vanished += 1
            stats.truncation_reasons.add(REASON_ROTATION_RACE)
            return False
        if (after.st_dev, after.st_ino) != (opened_stat.st_dev, opened_stat.st_ino):
            stats.files_vanished += 1
            stats.truncation_reasons.add(REASON_ROTATION_RACE)
            return False
        if after.st_size < size_at_open:
            stats.files_vanished += 1
            stats.truncation_reasons.add(REASON_ROTATION_RACE)
            return False
        return True

    def _deadline_hit(self, request: ScanRequest, stats: ScanStats) -> bool:
        if request.deadline_monotonic is not None and time.monotonic() > request.deadline_monotonic:
            stats.truncation_reasons.add(REASON_TIME_LIMIT)
            return True
        return False

    def _scan_range(
        self,
        handle: BinaryIO,
        file_name: str,
        start: int,
        size: int,
        request: ScanRequest,
        stats: ScanStats,
        series: list,
        wire_used: int,
    ) -> tuple[int, bool]:
        """Read [start, size), assemble CSV records, and feed matches through RLE."""
        handle.seek(start)
        window_from = request.window_from_ts[:_TS_COMPARE_LEN]
        window_to = request.window_to_ts[:_TS_COMPARE_LEN]
        rle = PhysicalRle(file_name, request.raw_record_cap)
        assembler = _LogicalRecordAssembler(request.raw_record_cap)
        pending = b""
        lineno = 0
        stop = False
        remaining = size - start  # never read past the size seen at open (T0 bound)
        while not stop and remaining > 0:
            if self._deadline_hit(request, stats):
                stop = True
                break
            chunk = handle.read(min(self._chunk_bytes, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            stats.scanned_bytes += len(chunk)
            pending += chunk
            lines = pending.split(b"\n")
            pending = lines.pop()  # unterminated tail: kept back (plan §15.4)
            for line in lines:
                lineno += 1
                if assembler.active:
                    assembler.continuation(lineno, line)
                else:
                    is_match = recall.matches(line, request.recall_clauses)
                    ts = ts_prefix(line)
                    if not _looks_like_ts(ts):
                        if is_match:
                            stats.dropped_lines += 1
                        continue
                    assembler.start(lineno, line, matched=is_match)
                if assembler.in_quotes:
                    continue
                first_lineno, last_lineno, raw, raw_truncated, is_match = assembler.take()
                if not is_match:
                    continue
                ts = ts_prefix(raw)
                stamp = ts[:_TS_COMPARE_LEN]
                if stamp < window_from or stamp > window_to:
                    # Out-of-window records (including a series head before
                    # the boundary) must not be counted — review finding.
                    continue
                stats.matched_lines += 1
                emitted = rle.feed(
                    first_lineno,
                    raw,
                    last_lineno=last_lineno,
                    raw_truncated=raw_truncated,
                )
                if emitted is not None:
                    wire_used, stop = self._emit(emitted, series, wire_used, request, stats)
                    if stop:
                        break
        if pending:
            stats.dropped_lines += 1  # in-flight write without trailing newline
            assembler.discard()
        elif assembler.active and assembler.discard():
            stats.dropped_lines += 1  # matched logical record has no closing CSV quote
        emitted = rle.flush()
        if emitted is not None and not stop:
            wire_used, stop = self._emit(emitted, series, wire_used, request, stats)
        return wire_used, stop

    @staticmethod
    def _emit(emitted, series: list, wire_used: int, request: ScanRequest, stats: ScanStats):
        """Hard wire budget: cost is checked BEFORE the series is retained."""
        cost = len(emitted.raw_record) + _SERIES_WIRE_OVERHEAD
        if wire_used + cost > request.wire_budget_bytes:
            stats.truncation_reasons.add(REASON_RETURN_LIMIT)
            return wire_used, True
        series.append(emitted)
        return wire_used + cost, False
