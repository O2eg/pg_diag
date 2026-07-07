"""Runtime configuration constants."""

from __future__ import annotations

import math

MIN_SUPPORTED_PG_VERSION = 140000
MAX_SUPPORTED_PG_VERSION = 189999

SUPPORTED_CONTENT_SCHEMA_VERSION = 2
ARTIFACT_SCHEMA_VERSION = 1

DEFAULT_COLLECTION_MODE = "remote-db-only"
LOCAL_COLLECTION_MODE = "local"
REMOTE_DB_ONLY_COLLECTION_MODE = "remote-db-only"

SNAPSHOT_MODE = "snapshot"
SNAPSHOTS_MODE = "snapshots"

SNAPSHOTS_MIN_DURATION_SECONDS = 30.0
SNAPSHOTS_DEFAULT_DURATION_SECONDS = 30.0
SNAPSHOTS_MAX_DURATION_SECONDS = 24 * 60 * 60.0

SNAPSHOTS_MIN_INTERVAL_SECONDS = 5.0
SNAPSHOTS_DEFAULT_INTERVAL_SECONDS = 15.0
SNAPSHOTS_MAX_INTERVAL_SECONDS = 600.0

SNAPSHOTS_MAX_SAMPLE_COUNT = 300


def snapshots_sample_count(duration_seconds: float, interval_seconds: float) -> int:
    return max(1, int(round(float(duration_seconds) / float(interval_seconds))) + 1)


def min_interval_for_snapshot_limit(duration_seconds: float) -> int:
    required = math.ceil(float(duration_seconds) / (SNAPSHOTS_MAX_SAMPLE_COUNT - 1))
    return max(int(SNAPSHOTS_MIN_INTERVAL_SECONDS), required)


def validate_snapshots_window(duration_seconds: float, interval_seconds: float) -> str | None:
    try:
        duration = float(duration_seconds)
        interval = float(interval_seconds)
    except (TypeError, ValueError):
        return "snapshots requires numeric --duration-seconds and --interval-seconds"
    if not math.isfinite(duration) or not math.isfinite(interval):
        return "snapshots requires finite --duration-seconds and --interval-seconds"
    if duration < SNAPSHOTS_MIN_DURATION_SECONDS or duration > SNAPSHOTS_MAX_DURATION_SECONDS:
        return (
            "snapshots requires --duration-seconds between "
            f"{_format_seconds(SNAPSHOTS_MIN_DURATION_SECONDS)} and {_format_seconds(SNAPSHOTS_MAX_DURATION_SECONDS)}"
        )
    if interval < SNAPSHOTS_MIN_INTERVAL_SECONDS or interval > SNAPSHOTS_MAX_INTERVAL_SECONDS:
        return (
            "snapshots requires --interval-seconds between "
            f"{_format_seconds(SNAPSHOTS_MIN_INTERVAL_SECONDS)} and {_format_seconds(SNAPSHOTS_MAX_INTERVAL_SECONDS)}"
        )
    sample_count = snapshots_sample_count(duration, interval)
    if sample_count > SNAPSHOTS_MAX_SAMPLE_COUNT:
        min_interval = min_interval_for_snapshot_limit(duration)
        return (
            f"snapshots sample count {sample_count} exceeds maximum {SNAPSHOTS_MAX_SAMPLE_COUNT}; "
            f"increase --interval-seconds to at least {min_interval}"
        )
    return None


def _format_seconds(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)
