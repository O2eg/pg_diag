"""Shared runtime and artifact contract values."""

from __future__ import annotations

from collections.abc import Mapping


COLLECTION_STATUSES = frozenset({"ok", "empty", "error", "unsupported", "skipped"})
RESULT_KINDS = frozenset({"none", "plain_text", "table", "chart"})
SEVERITY_LEVELS = frozenset({"high", "medium", "ok", "unknown"})

DATABASE_SCOPE_ALL = "all_databases"
DATABASE_SCOPE_CURRENT = "current_database"
DATABASE_SCOPES = frozenset({DATABASE_SCOPE_ALL, DATABASE_SCOPE_CURRENT})

INTERVAL_OK = "ok"
INTERVAL_NO_ACTIVITY = "no_activity"
INTERVAL_MISSING_START = "missing_start"
INTERVAL_MISSING_END = "missing_end"
INTERVAL_EPOCH_CHANGED = "epoch_changed"
INTERVAL_COUNTER_DECREASE = "counter_decrease"
INTERVAL_INVALID_VALUE = "invalid_value"
INTERVAL_INVALID_INTERVAL = "invalid_interval"

INTERVAL_STATUS_ORDER = (
    INTERVAL_OK,
    INTERVAL_NO_ACTIVITY,
    INTERVAL_MISSING_START,
    INTERVAL_MISSING_END,
    INTERVAL_EPOCH_CHANGED,
    INTERVAL_COUNTER_DECREASE,
    INTERVAL_INVALID_VALUE,
    INTERVAL_INVALID_INTERVAL,
)
INTERVAL_COVERAGE_STATUSES = frozenset(INTERVAL_STATUS_ORDER)
INTERVAL_COMPARABLE_STATUSES = frozenset({INTERVAL_OK, INTERVAL_NO_ACTIVITY})
INTERVAL_UNMATCHED_STATUSES = frozenset({INTERVAL_MISSING_START, INTERVAL_MISSING_END})
INTERVAL_INVALID_STATUSES = frozenset(
    {
        INTERVAL_EPOCH_CHANGED,
        INTERVAL_COUNTER_DECREASE,
        INTERVAL_INVALID_VALUE,
        INTERVAL_INVALID_INTERVAL,
    }
)


def interval_coverage_totals(counts: Mapping[str, int]) -> dict[str, int]:
    """Return the canonical interval coverage rollup for per-status counts."""
    return {
        "total": sum(counts.values()),
        "comparable": sum(counts.get(status, 0) for status in INTERVAL_COMPARABLE_STATUSES),
        "unmatched": sum(counts.get(status, 0) for status in INTERVAL_UNMATCHED_STATUSES),
        "invalid": sum(counts.get(status, 0) for status in INTERVAL_INVALID_STATUSES),
    }
