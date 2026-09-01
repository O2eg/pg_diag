"""Run-length encoding layers (plan §3, §15.4-15.5).

Two independent layers:

* :class:`PhysicalRle` — transport-level, provably safe: collapses only
  physically adjacent records whose identity fields (user, database, pid,
  client) AND record tail are byte-identical. Never merges across files or
  ranges.
* :func:`merge_client_series` — item-facing stream RLE over parsed, sanitized
  records: same fingerprint AND same identity (user, database, client host),
  bounded time gap.

Identity must survive both layers: merging records of different users into one
series silently misattributes events (review finding, 2026-08-31).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable, Iterator

from .model import RawSeries

_PREFIX_FIELDS = 11  # log_time .. transaction_id
_IDENTITY_FIELDS = frozenset({1, 2, 3, 4})  # user, database, pid, connection_from
_QUOTE = 0x22
_COMMA = 0x2C


def split_key(line: bytes, fields: int = _PREFIX_FIELDS) -> tuple[bytes, bytes] | None:
    """Return ``(identity, tail)`` for one csvlog line, or None.

    ``identity`` is the raw byte slice of the user/database/pid/client fields;
    ``tail`` is everything after the leading ``fields`` CSV fields. Explicit
    quote-aware byte scanner (no regex: awk dialects disagree on ``{n}``; this
    is also the reference model for the harvester's awk scanner).
    """
    commas = 0
    in_quotes = False
    index = 0
    length = len(line)
    field_start = 0
    identity_parts: list[bytes] = []
    while index < length:
        byte = line[index]
        if in_quotes:
            if byte == _QUOTE:
                if index + 1 < length and line[index + 1] == _QUOTE:
                    index += 2
                    continue
                in_quotes = False
        elif byte == _QUOTE:
            in_quotes = True
        elif byte == _COMMA:
            if commas in _IDENTITY_FIELDS:
                identity_parts.append(line[field_start:index])
            commas += 1
            field_start = index + 1
            if commas == fields:
                return b",".join(identity_parts), line[index + 1 :]
        index += 1
    return None


def strip_prefix(line: bytes, fields: int = _PREFIX_FIELDS) -> bytes | None:
    """Exact tail after the leading CSV fields (compatibility helper)."""
    parts = split_key(line, fields)
    return None if parts is None else parts[1]


def ts_prefix(line: bytes) -> str:
    """Leading log_time field (never quoted in csvlog)."""
    comma = line.find(b",")
    raw = line if comma < 0 else line[:comma]
    return raw.decode("ascii", errors="replace")


def client_host(connection_from: str | None) -> str | None:
    """Drop the ephemeral client port: every connection attempt has a new one."""
    if connection_from is None:
        return None
    host, separator, port = connection_from.rpartition(":")
    if separator and port.isdigit():
        return host
    return connection_from


class PhysicalRle:
    """Collapse physically adjacent identical records within one file."""

    def __init__(self, file_name: str, raw_record_cap: int) -> None:
        self._file = file_name
        self._cap = raw_record_cap
        self._key: tuple[bytes, bytes] | None = None
        self._count = 0
        self._first_lineno = 0
        self._last_lineno = 0
        self._first_ts = ""
        self._last_ts = ""
        self._raw: bytes = b""
        self._raw_truncated = False

    def feed(self, lineno: int, line: bytes) -> RawSeries | None:
        """Feed one matched physical line; may emit the previous run."""
        parts = split_key(line)
        key: tuple[bytes, bytes]
        if parts is not None:
            key = parts
        else:
            key = (b"\x00unparsed", str(lineno).encode())
        ts = ts_prefix(line)
        if self._count and key == self._key and lineno == self._last_lineno + 1:
            self._count += 1
            self._last_lineno = lineno
            self._last_ts = ts
            return None
        emitted = self.flush()
        self._key = key
        self._count = 1
        self._first_lineno = self._last_lineno = lineno
        self._first_ts = self._last_ts = ts
        self._raw = line[: self._cap]
        self._raw_truncated = len(line) > self._cap
        return emitted

    def flush(self) -> RawSeries | None:
        if not self._count:
            return None
        series = RawSeries(
            file=self._file,
            first_lineno=self._first_lineno,
            last_lineno=self._last_lineno,
            count=self._count,
            first_ts=self._first_ts,
            last_ts=self._last_ts,
            raw_record=self._raw,
            raw_truncated=self._raw_truncated,
        )
        self._count = 0
        return series


_FINGERPRINT_NUMBER_RE = re.compile(r"\d+")
_FINGERPRINT_WS_RE = re.compile(r"\s+")


def fingerprint(sanitized_message: str) -> str:
    """Group key: hash of the FULL normalized text.

    Truncating the normalized text before hashing merged distinct messages
    sharing a long prefix (review finding); the display sample is a separate
    concern of each item.
    """
    text = _FINGERPRINT_NUMBER_RE.sub("N", sanitized_message)
    text = _FINGERPRINT_WS_RE.sub(" ", text).strip()
    return hashlib.blake2b(text.encode("utf-8", "replace"), digest_size=12).hexdigest()


def merge_client_series(
    records: Iterable,  # LogRecord-shaped; ascending by log_time
    *,
    gap_seconds: float,
    merge: Callable,
    can_merge: Callable | None = None,
) -> Iterator:
    """Stream-RLE over an item's record stream (plan §3, client layer).

    Merges only records that agree on fingerprint, severity, SQLSTATE, AND
    identity (user, database, client host) within the time gap, so grouping
    dimensions used by items stay exact.
    """
    head = None
    for record in records:
        if head is not None:
            same = (
                record.severity == head.severity
                and record.sql_state == head.sql_state
                and record.fingerprint == head.fingerprint
                and record.user_name == head.user_name
                and record.database_name == head.database_name
                and client_host(record.connection_from) == client_host(head.connection_from)
            )
            gap = (record.log_time - head.last_time).total_seconds()
            if same and 0 <= gap <= gap_seconds and (can_merge is None or can_merge(head, record)):
                head = merge(head, record)
                continue
            yield head
        head = record
    if head is not None:
        yield head
