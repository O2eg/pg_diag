"""Data model and policy constants for server log scanning.

The logscan package is deliberately isolated: it depends only on the standard
library and exposes a small surface to the collection pipeline. See the plan in
``other/pg_diag_log_items_plan_20260831.md`` (revision 3.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# --- policy defaults (candidates for report.yaml: runtime_policy.server_log) ---

CHUNK_BYTES = 1_048_576
RAW_RECORD_CAP = 8_192
AUTO_EXPLAIN_RAW_RECORD_CAP = 512 * 1024
LINE_CAP = 2_000
# Full-detail plans from metadata/analytical workloads can exceed 64 KiB each
# and tens of MiB over a diagnostic window. Keep bounded collection without
# exhausting the transport budget after only a few minutes of such activity.
SCAN_BUDGET_BYTES = 512 * 1_048_576
WIRE_BUDGET_BYTES = 128 * 1_048_576
SERIES_GAP_SECONDS = 60.0
PHASE_WALLCLOCK_SECONDS = 60.0
MAX_CANDIDATE_FILES = 64
PROBE_BYTES = 16_384
MAX_PROBE_DOUBLINGS = 6
DEPTH_MAX_MINUTES = 1_440
DEPTH_DEFAULT_MINUTES = 10
# Directory discovery (logs mode): bounded per-file head/tail probes replace
# pg_ls_logdir() and the server clock. Probes double until a complete CSV
# record is found or MAX_PROBE_BYTES is reached; the file that anchors the
# window is additionally verified with exact quote parity from its start,
# bounded by VERIFY_BUDGET_BYTES.
MAX_PROBE_FILES = 1_024
HEAD_PROBE_BYTES = 4_096
TAIL_PROBE_BYTES = 16_384
MAX_PROBE_BYTES = 64 * 1_048_576
VERIFY_BUDGET_BYTES = 512 * 1_048_576

# --- truncation / degradation reasons (sorted tuples in artifacts) ---

REASON_SCAN_LIMIT = "scan_limit_hit"
REASON_RETURN_LIMIT = "return_limit_hit"
REASON_TIME_LIMIT = "time_limit_hit"
REASON_ROTATION_RACE = "rotation_race"
REASON_PARSE_ERRORS = "parse_errors"
REASON_NON_MONOTONIC = "non_monotonic_timestamps"
REASON_CANDIDATE_LIMIT = "candidate_limit_hit"
REASON_UNREADABLE = "files_unreadable"
REASON_DISCOVERY_INCOMPLETE = "discovery_incomplete"


@dataclass(frozen=True)
class LogFileInfo:
    """One candidate ``*.csv`` file from pg_ls_logdir()."""

    name: str
    size: int
    modification: datetime


@dataclass(frozen=True)
class ProbedFile:
    """One ``*.csv`` file discovered directly in a log directory.

    ``last_ts`` is the log_time of the last complete CSV record (the file's
    own clock, no timezone mapping), found by a quote-parity scan of the tail;
    ``determined`` is False when the probe cap was reached before a
    consistent parse, so the file may hold newer records than known.
    ``columns``/``severity`` come from the first complete record and detect
    the csvlog layout and the message locale. ``mtime`` is None when the
    transport cannot report it.
    """

    name: str
    size: int
    mtime: float | None
    last_ts: str | None
    columns: int | None
    severity: str | None
    determined: bool = True
    # A tail parse may be excluded from the window only when it is exact
    # (started at byte 0 or verified) or trusted: parity closes, the last
    # complete record ends at the final newline, and every record starts with
    # a timestamp. Anything else is verified with exact parity before exclusion.
    exact: bool = False
    trusted: bool = False


@dataclass(frozen=True)
class RawSeries:
    """Transport-level run: physically adjacent identical logical records.

    ``raw_record`` is the untruncated-or-capped raw CSV record of the run;
    parsing, sanitizing, and display truncation happen on the collector only.
    """

    file: str
    first_lineno: int
    last_lineno: int
    count: int
    first_ts: str
    last_ts: str
    raw_record: bytes
    raw_truncated: bool = False


@dataclass
class ScanStats:
    """Counters accumulated by a LogScanSource implementation."""

    scanned_bytes: int = 0
    matched_lines: int = 0
    dropped_lines: int = 0
    files_seen: int = 0
    files_read: int = 0
    files_vanished: int = 0
    files_unreadable: int = 0
    truncation_reasons: set[str] = field(default_factory=set)


@dataclass
class ScanResult:
    series: list[RawSeries]
    stats: ScanStats
    covered_from_ts: str | None = None
    covered_to_ts: str | None = None


@dataclass(frozen=True)
class ScanRequest:
    """Input for one LogScanSource.scan() call."""

    log_directory: str
    files: tuple[LogFileInfo, ...]  # newest first; the oldest may span the boundary
    window_from_ts: str  # "YYYY-MM-DD HH:MI:SS" in log_timezone (server-formatted)
    window_to_ts: str  # upper bound (server T0); records after it are out of scope
    recall_clauses: tuple[tuple[bytes, ...], ...]
    scan_budget_bytes: int = SCAN_BUDGET_BYTES
    wire_budget_bytes: int = WIRE_BUDGET_BYTES
    raw_record_cap: int = RAW_RECORD_CAP
    deadline_monotonic: float | None = None  # cooperative wall-clock stop


@dataclass(frozen=True)
class LogRecord:
    """A client-side series (RLE over an item's record stream)."""

    log_time: datetime
    last_time: datetime
    repeat_count: int
    severity: str
    sql_state: str | None
    message: str  # sanitized, display-truncated to LINE_CAP
    user_name: str | None
    database_name: str | None
    process_id: int | None
    connection_from: str | None
    backend_type: str | None
    query_id: int | None
    partial: bool
    count_complete: bool
    encoding_degraded: bool
    fingerprint: str
    # Sanitized csvlog detail column. It is internal evidence bounded by
    # RAW_RECORD_CAP, not a display value bounded by LINE_CAP.
    detail: str | None = None
    auto_explain_plan: "AutoExplainPlan | None" = None
    session_id: str | None = None
    session_line_num: int | None = None
    command_tag: str | None = None
    session_start_time: datetime | None = None
    transaction_id: int | None = None
    application_name: str | None = None
    query: str | None = None
    context: str | None = None
    # Full sanitized csvlog message, bounded by ScanRequest.raw_record_cap.
    # Item parsers use it for metrics that may appear after LINE_CAP.
    message_full: str | None = None
    # UTC offset of this record's wall-clock timestamp when the log clock is
    # known; charts place records with it instead of one window-wide offset.
    utc_offset_seconds: int | None = None


@dataclass(frozen=True)
class AutoExplainPlan:
    """Safe metadata extracted from one auto_explain log record.

    ``viewer_plan`` retains only the collector-sanitized record, bounded by the
    auto_explain raw-record cap, so the self-contained report can open it in the
    embedded read-only plan viewer without exposing the original log text. The
    optional query sample is sanitized and capped at 300 characters for the
    chart tooltip; format/root/node metadata proves that the multiline plan
    itself was recognized rather than loosely matched.
    """

    duration_ms: float
    plan_format: str
    root_node_type: str | None
    node_count: int
    parsed: bool
    complete: bool
    query_sample: str | None
    viewer_plan: str | None = None


@dataclass(frozen=True)
class LogCoverage:
    requested_minutes: int
    covered_from: str | None
    covered_to: str | None
    files_seen: int
    files_read: int
    files_vanished: int
    files_unreadable: int
    scanned_bytes: int
    matched_lines: int
    parsed_records: int
    dropped_lines: int
    window_truncated: bool
    truncation_reasons: tuple[str, ...]
    ranking_complete: bool
    locale_supported: bool
    requested_from: str | None = None
    requested_to: str | None = None


@dataclass(frozen=True)
class ServerLogContext:
    """What deferred server_log item sources receive.

    ``inventory`` (pg_ls_logdir listing + logging GUCs) is populated whenever
    the flag was given and the database answered — even when log CONTENT is
    unavailable — so the log_inventory capability items keep working.
    """

    window: "LogWindow | None"
    marker: dict
    inventory: "dict | None" = None
    mode: str | None = None
    interval_seconds: float | None = None


@dataclass(frozen=True)
class LogWindow:
    """The one-per-report parsed log window consumed by report items."""

    records: tuple[LogRecord, ...]  # ascending by log_time
    coverage: LogCoverage
