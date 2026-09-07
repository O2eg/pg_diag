"""Byte-level csvlog record boundaries by CSV quote parity.

Shared by the local scan source (window-start alignment), the directory
probes, and the tests. A csvlog field may contain newlines, so a physical line
that starts with a date is a record start only when the quote parity in front
of it is even.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .csvparse import parse_timestamp
from .rle import ts_prefix

_QUOTE = 0x22
_TS_LINE_RE = re.compile(rb"^\d{4}-\d{2}-\d{2} ")


def quote_state(line: bytes, in_quotes: bool) -> bool:
    """Quote parity after ``line`` given the parity before it (CSV doubling aware)."""
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


def complete_records(
    data: bytes,
    *,
    partial_first_line: bool,
    initial_parity: bool = False,
) -> tuple[list[tuple[int, int]], bool]:
    """Byte ranges of complete CSV records in ``data`` and the final parity.

    With ``partial_first_line`` the bytes up to the first newline belong to a
    line that began before the chunk: they cannot start a record, but their
    quotes still move parity. A record starts at a line beginning with even
    parity and completes at the first newline-terminated line where parity is
    even again. The returned parity is False when the data ends outside
    quotes; a tail probe whose parity ends odd was started inside a quoted
    field (or the file ends inside an unfinished record) and must not be
    trusted.
    """
    position = 0
    parity = initial_parity
    if partial_first_line:
        newline = data.find(b"\n")
        if newline < 0:
            return [], quote_state(data, parity)
        parity = quote_state(data[:newline], parity)
        position = newline + 1
    ranges: list[tuple[int, int]] = []
    record_start: int | None = None  # unknown while inside a record that began earlier
    while position < len(data):
        newline = data.find(b"\n", position)
        if newline < 0:
            break  # unterminated tail: an in-flight write, never trusted
        if not parity:
            record_start = position
        parity = quote_state(data[position:newline], parity)
        if not parity and record_start is not None:
            ranges.append((record_start, newline + 1))
        position = newline + 1
    return ranges, parity


def record_timestamp(data: bytes, span: tuple[int, int]) -> str | None:
    """log_time of the record in ``span``, or None when its head is no record."""
    start, end = span
    line_end = data.find(b"\n", start, end)
    line = data[start : line_end if line_end >= 0 else end]
    if not _TS_LINE_RE.match(line):
        return None
    ts = ts_prefix(line)
    return ts if parse_timestamp(ts) is not None else None


@dataclass(frozen=True)
class TailParse:
    last_ts: str | None
    consistent: bool  # parity even at the end of the chunk
    trusted: bool  # consistent, last record ends at the final newline, all records stamped


def parse_tail(
    data: bytes,
    *,
    partial_first_line: bool,
    initial_parity: bool = False,
) -> TailParse:
    ranges, parity = complete_records(
        data, partial_first_line=partial_first_line, initial_parity=initial_parity
    )
    stamps = [record_timestamp(data, span) for span in ranges]
    last = next((stamp for stamp in reversed(stamps) if stamp is not None), None)
    consistent = not parity
    trusted = (
        consistent
        and bool(ranges)
        and ranges[-1][1] == len(data)
        and all(stamp is not None for stamp in stamps)
    )
    return TailParse(last, consistent, trusted)


def plausible_record_start(data: bytes) -> bool:
    """``data`` begins at a record boundary and every complete record is stamped.

    Used to validate a binary-search alignment inside a file: a position
    inside a quoted multiline message yields unstamped "records" (its
    continuation lines) and is rejected.
    """
    ranges, _parity = complete_records(data, partial_first_line=False)
    return bool(ranges) and all(record_timestamp(data, span) is not None for span in ranges)
