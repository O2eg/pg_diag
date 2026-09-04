"""Shared helpers for server_log item sources (content/python/server_log/*).

Sources stay thin: each owns only its aggregation. Status mapping follows the
plan (§7): flag absent -> skipped; no reader / csvlog off -> unsupported;
phase failure -> error; full empty window -> empty. Items that parse localized
severity or message text opt into the English-locale requirement explicitly.
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from .model import LogRecord, LogWindow
from .rle import client_host

__all__ = [
    "SEVERITY_ERRORS",
    "client_host",
    "coverage_note",
    "empty_result_status",
    "fmt_time",
    "is_recovery_end_of_wal",
    "message_contains_any",
    "resolve_english_window",
    "resolve_inventory",
    "resolve_window",
    "severity_rank",
]

SEVERITY_ERRORS = ("ERROR", "FATAL", "PANIC")
_SEVERITY_RANK = {"WARNING": 1, "ERROR": 2, "FATAL": 3, "PANIC": 4}
_END_OF_WAL_RE = re.compile(
    r"invalid record length at [0-9A-F]+/[0-9A-F]+: expected at least \d+, got 0",
    re.IGNORECASE,
)


def is_recovery_end_of_wal(record: LogRecord) -> bool:
    """A startup LOG at zero-length WAL is not, by itself, corruption evidence.

    PostgreSQL 10-12 have no backend_type CSV column. Explicit error SQLSTATEs
    and severities must retain their incident classification in every version.
    """
    return (
        record.severity == "LOG"
        and record.sql_state == "00000"
        and record.backend_type in (None, "startup")
        and _END_OF_WAL_RE.fullmatch(record.message.strip()) is not None
    )


def resolve_window(context: Any) -> tuple[LogWindow | None, dict[str, Any] | None]:
    """Return (window, early_status) for a server_log item source.

    ``early_status`` is a dict {collection_status, reason} when the item must
    not evaluate rows (phase skipped/unavailable/failed). Locale-independent
    items can consume the returned window for every ``lc_messages`` value.
    """
    server_log = getattr(context, "server_log", None)
    if server_log is None or not isinstance(getattr(server_log, "marker", None), dict):
        return None, {
            "collection_status": "error",
            "reason": "server log phase did not run before this item",
        }
    marker = server_log.marker
    status = marker.get("status")
    reason = marker.get("reason")
    if status == "skipped":
        return None, {"collection_status": "skipped", "reason": reason}
    if status == "unavailable":
        return None, {"collection_status": "unsupported", "reason": reason}
    if status == "error":
        return None, {"collection_status": "error", "reason": reason}
    window = server_log.window
    if window is None:
        return None, {
            "collection_status": "error",
            "reason": "log collection reported success but produced no window",
        }
    return window, None


def resolve_english_window(context: Any) -> tuple[LogWindow | None, dict[str, Any] | None]:
    """Resolve a window for an item that parses English severity/message text.

    PostgreSQL localizes csvlog severity and message fields. Keeping this check
    item-specific lets SQLSTATE-driven items work in every locale without
    allowing English-pattern items to claim a false empty result.
    """
    window, early = resolve_window(context)
    if early is not None or window is None:
        return window, early
    if not window.coverage.locale_supported:
        return None, {
            "collection_status": "unsupported",
            "reason": (
                "this item parses localized csvlog severity or message text, but "
                "lc_messages is not C/POSIX/en_*"
            ),
        }
    return window, None


def resolve_inventory(context: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Like resolve_window, but for log_inventory capability items.

    The inventory stays valid even when log CONTENT is unavailable (csvlog off,
    no reader): only a disabled flag or a pre-listing failure blocks it.
    """
    server_log = getattr(context, "server_log", None)
    if server_log is None or not isinstance(getattr(server_log, "marker", None), dict):
        return None, {
            "collection_status": "error",
            "reason": "server log phase did not run before this item",
        }
    marker = server_log.marker
    if marker.get("status") == "skipped":
        return None, {"collection_status": "skipped", "reason": marker.get("reason")}
    inventory = getattr(server_log, "inventory", None)
    if inventory is None:
        status = "unsupported" if marker.get("status") == "unavailable" else "error"
        return None, {"collection_status": status, "reason": marker.get("reason")}
    return inventory, None


def severity_rank(severity: str) -> int:
    return _SEVERITY_RANK.get(severity, 0)


def fmt_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def coverage_note(window: LogWindow) -> str | None:
    """Human note when the window is incomplete; None when coverage is full."""
    coverage = window.coverage
    if coverage.ranking_complete:
        return None
    reasons = ", ".join(coverage.truncation_reasons) or "window truncated"
    return (
        f"Counts are lower bounds over the covered part of the window "
        f"({coverage.covered_from or '?'} .. {coverage.covered_to or '?'}; {reasons})."
    )


def empty_result_status(window: LogWindow) -> tuple[str, str, dict[str, Any]]:
    """Status for an item with zero rows.

    ``empty`` promises "verified: nothing happened" — it may only be claimed
    when the full window was provably read (review finding, 2026-08-31).
    """
    if window.coverage.ranking_complete:
        return "empty", "ok", {}
    reasons = ", ".join(window.coverage.truncation_reasons) or "window incomplete"
    issues = {
        "summary": {
            "severity": "unknown",
            "status": "review",
            "title": "No events found, but the log window is incomplete",
            "description": (
                f"The collected window is not complete ({reasons}); the absence of "
                "matching events is not proven."
            ),
            "recommendation": (
                "Check runtime.log_collection coverage and re-run with a smaller "
                "--log-depth-time-min or fixed log access before trusting the result."
            ),
        },
        "items": [],
    }
    return "ok", "unknown", issues


def message_contains_any(record: LogRecord, fragments: tuple[str, ...]) -> bool:
    message = record.message
    return any(fragment in message for fragment in fragments)
