"""The log clock: how csvlog wall-clock timestamps map to absolute instants.

csvlog writes ``log_time`` as local wall time in ``log_timezone`` followed by
the zone abbreviation (``MSK``, ``CEST``) or a numeric offset (``+03``). The
database path knows the zone name; the directory path (logs mode) knows only
what the suffix says unless ``--log-timezone`` names the IANA zone. Window
arithmetic must happen on absolute time: across a DST transition two records
seven minutes apart differ by 67 wall-clock minutes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .csvparse import parse_timestamp


@dataclass(frozen=True)
class LogClock:
    """Zone knowledge for one log window.

    ``zone`` resolves every record exactly (the suffix disambiguates the
    repeated hour of a fall-back transition); ``fixed_offset`` covers numeric
    suffixes and UTC; both None means the offset is unknown and only naive
    wall-clock arithmetic is possible.
    """

    label: str
    zone: ZoneInfo | None = None
    fixed_offset: int | None = None

    @property
    def known(self) -> bool:
        return self.zone is not None or self.fixed_offset is not None

    def offset_for(self, naive: datetime, suffix: str | None) -> int | None:
        """UTC offset in seconds of a wall-clock instant, or None when unknown."""
        if self.zone is not None:
            aware = self._aware(naive, suffix)
            offset = aware.utcoffset() or timedelta(0)
            return int(offset.total_seconds())
        return self.fixed_offset

    def to_absolute(self, naive: datetime, suffix: str | None) -> datetime | None:
        """Aware UTC instant of a wall-clock timestamp, or None when unknown."""
        if self.zone is not None:
            return self._aware(naive, suffix).astimezone(timezone.utc)
        if self.fixed_offset is not None:
            return (naive - timedelta(seconds=self.fixed_offset)).replace(tzinfo=timezone.utc)
        return None

    def to_local(self, absolute: datetime) -> datetime:
        """Naive wall-clock timestamp of an absolute instant."""
        if self.zone is not None:
            return absolute.astimezone(self.zone).replace(tzinfo=None)
        offset = self.fixed_offset or 0
        return absolute.astimezone(timezone.utc).replace(tzinfo=None) + timedelta(seconds=offset)

    def _aware(self, naive: datetime, suffix: str | None) -> datetime:
        assert self.zone is not None
        first = naive.replace(tzinfo=self.zone, fold=0)
        if suffix and any(ch.isalpha() for ch in suffix):
            second = naive.replace(tzinfo=self.zone, fold=1)
            if first.tzname() != suffix and second.tzname() == suffix:
                return second
        return first


def zone_suffix(value: str | None) -> str | None:
    """The zone suffix of a raw csvlog timestamp (``MSK``, ``+03``), if any."""
    if not value:
        return None
    head, _, tail = value.rpartition(" ")
    if head and tail and (any(ch.isalpha() for ch in tail) or tail[:1] in "+-"):
        return tail
    return None


@dataclass(frozen=True)
class WindowBounds:
    """Window ends in the clock's own units.

    ``window_from`` is the wall-clock time of the absolute window start and is
    what coverage reports; ``scan_from``/``scan_to`` are the earliest and
    latest wall-clock stamps any window record can carry, widened across a
    DST transition so that the string-comparing scanners never drop a record
    that the absolute filter would keep (after a fall-back a record inside the
    window may carry a wall-clock stamp later than the anchor's).
    ``anchor_abs``/``from_abs`` are None when the clock is unknown.
    """

    window_to: str
    window_from: str
    scan_from: str
    scan_to: str
    anchor_abs: datetime | None
    from_abs: datetime | None


def window_bounds(anchor_ts: str, depth_minutes: int, clock: LogClock) -> WindowBounds:
    anchor = parse_timestamp(anchor_ts)
    assert anchor is not None
    depth = timedelta(minutes=depth_minutes)
    window_to = anchor.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    naive_from = anchor - depth
    anchor_abs = clock.to_absolute(anchor, zone_suffix(anchor_ts))
    if anchor_abs is None:
        stamp = naive_from.strftime("%Y-%m-%d %H:%M:%S")
        return WindowBounds(window_to, stamp, stamp, window_to, None, None)
    from_abs = anchor_abs - depth
    local_from = clock.to_local(from_abs)
    # A transition inside the window shifts wall-clock time by up to the
    # offset difference; the scan bounds take the widest interpretation and
    # the absolute filter decides afterwards.
    offset_from = clock.offset_for(local_from, None) or 0
    offset_to = clock.offset_for(anchor, zone_suffix(anchor_ts)) or 0
    shift = timedelta(seconds=abs(offset_from - offset_to))
    scan_from = min(local_from, naive_from) - shift
    scan_to = anchor + shift
    return WindowBounds(
        window_to,
        local_from.strftime("%Y-%m-%d %H:%M:%S"),
        scan_from.strftime("%Y-%m-%d %H:%M:%S"),
        scan_to.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        anchor_abs,
        from_abs,
    )
