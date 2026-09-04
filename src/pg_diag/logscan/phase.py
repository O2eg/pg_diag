"""Server-log collection phase (plan §4, §7).

Runs after report items (and after snapshots), before DDL extraction; must
never fail the report. Writes the structured ``runtime['log_collection']``
marker: ``{"status", "reason", "coverage"}``.
"""

from __future__ import annotations

import asyncio
import posixpath
import re
import time
from dataclasses import asdict, replace
from typing import Any

from ..security import redact_error

from .auto_explain import parse_auto_explain
from .csvparse import parse_record, parse_timestamp
from .harvester import BashHarvesterSource, HarvesterUnavailableError
from .model import (
    AUTO_EXPLAIN_RAW_RECORD_CAP,
    DEPTH_MAX_MINUTES,
    LINE_CAP,
    MAX_CANDIDATE_FILES,
    PHASE_WALLCLOCK_SECONDS,
    RAW_RECORD_CAP,
    REASON_CANDIDATE_LIMIT,
    REASON_PARSE_ERRORS,
    SERIES_GAP_SECONDS,
    LogCoverage,
    LogFileInfo,
    LogRecord,
    LogWindow,
    RawSeries,
    ScanRequest,
    ScanResult,
    ScanStats,
    ServerLogContext,
)
from .item_recall import clauses_for_items
from .rle import fingerprint, merge_client_series
from .sanitize import sanitize_text
from .sources import LocalLogSource, LogScanSource

_INSUFFICIENT_PRIVILEGE = "42501"
_SUPPORTED_LOCALE_PREFIXES = ("C", "POSIX", "en_", "en.", "English")
_LOCK_WAIT_EVENT_RE = re.compile(
    r"^process \d+ (?:still waiting for|acquired) \w+ on .+ after \d+(?:\.\d+)? ms"
)

_PG_TO_PYTHON_ENCODING = {
    "UTF8": "utf-8",
    "LATIN1": "latin-1",
    "LATIN2": "iso8859-2",
    "LATIN9": "iso8859-15",
    "WIN1250": "cp1250",
    "WIN1251": "cp1251",
    "WIN1252": "cp1252",
    "KOI8R": "koi8-r",
    "EUC_JP": "euc_jp",
    "SQL_ASCII": "utf-8",
}

_FEASIBILITY_SQL = """
select
  current_setting('logging_collector') as logging_collector,
  current_setting('log_destination') as log_destination,
  current_setting('log_directory') as log_directory,
  current_setting('data_directory') as data_directory,
  current_setting('lc_messages') as lc_messages,
  current_setting('log_rotation_age') as log_rotation_age,
  current_setting('log_rotation_size') as log_rotation_size,
  current_setting('log_truncate_on_rotation') as log_truncate_on_rotation,
  current_setting('log_filename') as log_filename,
  current_setting('log_timezone') as log_timezone,
  current_setting('block_size')::int as block_size,
  extract(epoch from (
    (current_timestamp at time zone current_setting('log_timezone'))
      - (current_timestamp at time zone 'UTC')
  ))::int as log_utc_offset_seconds,
  current_setting('server_version_num')::int as server_version_num,
  pg_catalog.pg_current_logfile('csvlog') as current_csvlog,
  to_char(
    (pg_catalog.clock_timestamp() at time zone current_setting('log_timezone'))
      - pg_catalog.make_interval(mins => $1),
    'YYYY-MM-DD HH24:MI:SS') as window_from,
  to_char(
    pg_catalog.clock_timestamp() at time zone current_setting('log_timezone'),
    'YYYY-MM-DD HH24:MI:SS') as window_to
"""

# The mtime cutoff must be computed by the server: pg_ls_logdir() returns
# timestamptz while the window string is rendered in log_timezone — comparing
# them on the collector once dropped a rotated file (tz skew bug, 2026-08-31).
# The listing returns ALL csv files (bounded) with a server-computed
# ``in_window`` flag: scan candidates are the in-window subset, while the full
# listing feeds the log_inventory capability (log_files_overview).
_LOGDIR_SQL = """
select name, size, modification,
       (
         modification >= pg_catalog.clock_timestamp()
           - pg_catalog.make_interval(mins => $1)
         or name = $2
       ) as in_window
from pg_catalog.pg_ls_logdir()
where name like '%.csv'
order by modification desc
limit $3
"""

_LOGDIR_TOTALS_SQL = """
select count(*)::int as file_count, coalesce(sum(size), 0)::int8 as total_bytes
from pg_catalog.pg_ls_logdir()
where name like '%.csv'
"""

_ENCODING_SQL = """
select datname, pg_catalog.pg_encoding_to_char(encoding) as encoding
from pg_catalog.pg_database
"""


async def collect_report_server_log(run: Any, *, depth_minutes: int | None) -> LogWindow | None:
    """Collect and parse the csvlog window; record runtime['log_collection']."""
    if depth_minutes is None or depth_minutes == 0:
        _finish(
            run,
            None,
            {
                "status": "skipped",
                "reason": "log collection disabled (--log-depth-time-min not set)",
                "coverage": None,
            },
        )
        return None
    enabled_items = _enabled_server_log_items(run)
    if not enabled_items:
        _finish(
            run,
            None,
            {
                "status": "skipped",
                "reason": "no server_log items selected for this run",
                "coverage": None,
            },
        )
        return None
    try:
        inventory, window = await asyncio.wait_for(
            _collect(run, depth_minutes=min(int(depth_minutes), DEPTH_MAX_MINUTES)),
            timeout=PHASE_WALLCLOCK_SECONDS,
        )
    except _PhaseUnavailable as exc:
        _finish(
            run,
            None,
            {"status": exc.status, "reason": str(exc), "coverage": None},
            inventory=exc.inventory,
        )
        return None
    except (TimeoutError, asyncio.TimeoutError):
        _finish(
            run,
            None,
            {
                "status": "error",
                "reason": f"log collection exceeded {PHASE_WALLCLOCK_SECONDS:.0f}s wall clock",
                "coverage": None,
            },
        )
        return None
    except Exception as exc:  # noqa: BLE001 - the phase must never fail the report
        _finish(
            run,
            None,
            {
                "status": "error",
                "reason": f"{type(exc).__name__}: {redact_error(exc)}",
                "coverage": None,
            },
        )
        return None
    coverage = asdict(window.coverage)
    coverage["truncation_reasons"] = list(coverage["truncation_reasons"])
    _finish(
        run,
        window,
        {"status": "collected", "reason": None, "coverage": coverage},
        inventory=inventory,
    )
    return window


def _finish(
    run: Any,
    window: LogWindow | None,
    marker: dict[str, Any],
    *,
    inventory: dict[str, Any] | None = None,
) -> None:
    run.artifact["runtime"]["log_collection"] = marker
    runtime = run.artifact.get("runtime") or {}
    interval_seconds = runtime.get("interval_seconds")
    run.server_log = ServerLogContext(
        window=window,
        marker=marker,
        inventory=inventory,
        mode=str(runtime.get("mode")) if runtime.get("mode") is not None else None,
        interval_seconds=(
            float(interval_seconds) if isinstance(interval_seconds, (int, float)) else None
        ),
    )
    run.server_log_window = window


def _build_inventory(
    facts: Any,
    rows: Any,
    totals: Any,
    window_to: str,
) -> dict[str, Any]:
    """pg_ls_logdir listing plus logging GUCs for the log_inventory items."""
    current_basename = posixpath.basename(str(facts["current_csvlog"] or ""))
    files = []
    for row in rows:
        modification = row["modification"]
        naive = modification.replace(tzinfo=None) if modification.tzinfo else modification
        files.append(
            {
                "name": str(row["name"]),
                "size_bytes": int(row["size"]),
                "modification": naive.strftime("%Y-%m-%d %H:%M:%S"),
                "in_window": bool(row["in_window"]),
                "is_current": str(row["name"]) == current_basename,
            }
        )
    return {
        "files": files,
        "file_count_total": int(totals["file_count"]) if totals is not None else len(files),
        "total_bytes": int(totals["total_bytes"]) if totals is not None else 0,
        "window_from": str(facts["window_from"]),
        "collected_to": window_to,
        "settings": {
            "logging_collector": str(facts["logging_collector"]),
            "log_destination": str(facts["log_destination"]),
            "log_directory": str(facts["log_directory"]),
            "log_filename": str(facts["log_filename"]),
            "log_timezone": str(facts.get("log_timezone") or "UTC"),
            "log_utc_offset_seconds": int(facts.get("log_utc_offset_seconds") or 0),
            "block_size": int(facts.get("block_size") or 8192),
            "log_rotation_age": str(facts["log_rotation_age"]),
            "log_rotation_size": str(facts["log_rotation_size"]),
            "log_truncate_on_rotation": str(facts["log_truncate_on_rotation"]),
        },
    }


def _enabled_server_log_items(run: Any) -> tuple[str, ...]:
    plan = getattr(run, "plan", None)
    items = getattr(plan, "items", None)
    if items is None:
        return ()
    return tuple(
        planned.item_id
        for planned in items
        if planned.item_id.startswith("server_log.") and planned.status != "skipped"
    )


class _PhaseUnavailable(Exception):
    def __init__(
        self,
        message: str,
        *,
        status: str = "unavailable",
        inventory: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.inventory = inventory


async def _collect(run: Any, *, depth_minutes: int) -> tuple[dict[str, Any], LogWindow]:
    runtime = run.artifact["runtime"]
    if run.conn is None or not runtime.get("database_connected"):
        raise _PhaseUnavailable("log collection needs a database connection for GUC discovery")
    collection_mode = str(runtime.get("collection_mode") or "")
    try:
        facts = await run.conn.fetchrow(_FEASIBILITY_SQL, depth_minutes)
    except Exception as exc:
        if getattr(exc, "sqlstate", None) == _INSUFFICIENT_PRIVILEGE:
            raise _PhaseUnavailable(
                "insufficient privilege reading log GUCs; grant pg_monitor to the "
                "diagnostics role"
            ) from exc
        raise
    current_basename = posixpath.basename(str(facts["current_csvlog"] or ""))
    rows = await run.conn.fetch(
        _LOGDIR_SQL, depth_minutes, current_basename, MAX_CANDIDATE_FILES + 1
    )
    totals = await run.conn.fetchrow(_LOGDIR_TOTALS_SQL)
    window_from = str(facts["window_from"])
    window_to = str(facts["window_to"])
    inventory = _build_inventory(facts, rows[:MAX_CANDIDATE_FILES], totals, window_to)

    if str(facts["logging_collector"]).lower() not in ("on", "true", "1"):
        raise _PhaseUnavailable(
            "logging_collector is off; csvlog files are not produced",
            inventory=inventory,
        )
    destinations = {part.strip() for part in str(facts["log_destination"]).split(",")}
    if "csvlog" not in destinations:
        raise _PhaseUnavailable(
            f"csvlog is not in log_destination ({facts['log_destination']!r})",
            inventory=inventory,
        )
    if not facts["current_csvlog"]:
        raise _PhaseUnavailable("pg_current_logfile('csvlog') is empty", inventory=inventory)

    log_directory = str(facts["log_directory"])
    if not log_directory.startswith("/"):
        log_directory = posixpath.join(str(facts["data_directory"]), log_directory)
    locale_supported = str(facts["lc_messages"]).startswith(_SUPPORTED_LOCALE_PREFIXES)
    server_version_num = int(facts["server_version_num"])

    candidate_rows = [row for row in rows if row["in_window"]]
    # The listing is newest-first. Seeing an out-of-window row proves that all
    # omitted older rows are outside the requested window too; only 65
    # consecutive in-window rows mean the 64-file scan candidate cap was hit.
    candidate_overflow = len(rows) > MAX_CANDIDATE_FILES and all(row["in_window"] for row in rows)
    candidates: list[LogFileInfo] = []
    for row in candidate_rows[:MAX_CANDIDATE_FILES]:
        modification = row["modification"]
        naive = modification.replace(tzinfo=None) if modification.tzinfo else modification
        candidates.append(
            LogFileInfo(name=str(row["name"]), size=int(row["size"]), modification=naive)
        )
    if not candidates:
        raise _PhaseUnavailable("no csvlog files within the requested window", inventory=inventory)

    enabled_items = _enabled_server_log_items(run)
    clauses = clauses_for_items(enabled_items)
    if not clauses:
        # Only inventory-capability items are enabled: no content scan needed.
        result = ScanResult(series=[], stats=ScanStats(files_seen=len(candidates)))
    else:
        source = _select_source(collection_mode, log_directory, getattr(run, "ssh", None))
        request = ScanRequest(
            log_directory=log_directory,
            files=tuple(candidates),  # newest first from the SQL ordering
            window_from_ts=window_from,
            window_to_ts=window_to,
            recall_clauses=clauses,
            raw_record_cap=(
                AUTO_EXPLAIN_RAW_RECORD_CAP
                if "server_log.auto_explain_plans" in enabled_items
                else RAW_RECORD_CAP
            ),
            deadline_monotonic=time.monotonic() + PHASE_WALLCLOCK_SECONDS * 0.9,
        )
        try:
            result = await source.scan(request)
        except HarvesterUnavailableError as exc:
            raise _PhaseUnavailable(str(exc), inventory=inventory) from exc
        if result.stats.files_read == 0:
            raise _PhaseUnavailable(
                "no candidate csvlog file could be read; check filesystem permissions "
                "for the collector account (see docs/access-best-practices.md)",
                inventory=inventory,
            )
    if candidate_overflow:
        result.stats.truncation_reasons.add(REASON_CANDIDATE_LIMIT)
    encodings = await _database_encodings(run.conn)
    return inventory, _build_window(
        result,
        depth_minutes=depth_minutes,
        server_version_num=server_version_num,
        window_from=window_from,
        window_to=window_to,
        locale_supported=locale_supported,
        encodings=encodings,
    )


def _select_source(collection_mode: str, log_directory: str, ssh: Any) -> LogScanSource:
    if collection_mode == "local":
        return LocalLogSource(log_directory)
    if collection_mode == "remote":
        if ssh is None:
            raise _PhaseUnavailable("remote log collection needs the SSH transport")
        return BashHarvesterSource(ssh)
    raise _PhaseUnavailable("server log collection requires local or remote (SSH) collection mode")


async def _database_encodings(conn: Any) -> dict[str, str]:
    try:
        rows = await conn.fetch(_ENCODING_SQL)
    except Exception:  # noqa: BLE001 - encoding map is best-effort
        return {}
    return {
        str(row["datname"]): _PG_TO_PYTHON_ENCODING.get(str(row["encoding"]), "utf-8")
        for row in rows
    }


def _build_window(
    result: ScanResult,
    *,
    depth_minutes: int,
    server_version_num: int,
    window_from: str,
    window_to: str,
    locale_supported: bool,
    encodings: dict[str, str],
) -> LogWindow:
    stats = result.stats
    window_from_dt = parse_timestamp(window_from)
    window_to_dt = parse_timestamp(window_to)
    records: list[LogRecord] = []
    parse_errors = 0
    for series in result.series:
        record = _record_from_series(series, server_version_num, encodings)
        if record is None:
            parse_errors += 1
            continue
        if window_from_dt is not None and record.last_time < window_from_dt:
            continue
        if window_to_dt is not None and record.log_time > window_to_dt:
            continue  # written after the server-side T0 (growing active file)
        records.append(record)
    if parse_errors:
        stats.truncation_reasons.add(REASON_PARSE_ERRORS)
        stats.dropped_lines += parse_errors
    # Any loss — dropped matches, unreadable or vanished files, parse errors —
    # forfeits completeness: absence of events must never be overclaimed.
    ranking_complete = (
        not stats.truncation_reasons
        and stats.files_vanished == 0
        and stats.files_unreadable == 0
        and stats.dropped_lines == 0
    )
    if not ranking_complete:
        # With any global loss every count is only a lower bound: the lost
        # region could have held more occurrences of any series.
        records = [replace(record, count_complete=False) for record in records]
    records.sort(key=lambda record: (record.log_time, record.last_time))
    merged = list(
        merge_client_series(
            records,
            gap_seconds=SERIES_GAP_SECONDS,
            merge=_merge_records,
            can_merge=_can_merge_client_records,
        )
    )
    truncated = bool(stats.truncation_reasons)
    coverage = LogCoverage(
        requested_minutes=depth_minutes,
        covered_from=result.covered_from_ts,
        covered_to=result.covered_to_ts or window_to,
        files_seen=stats.files_seen,
        files_read=stats.files_read,
        files_vanished=stats.files_vanished,
        files_unreadable=stats.files_unreadable,
        scanned_bytes=stats.scanned_bytes,
        matched_lines=stats.matched_lines,
        parsed_records=len(records),
        dropped_lines=stats.dropped_lines,
        window_truncated=truncated,
        truncation_reasons=tuple(sorted(stats.truncation_reasons)),
        ranking_complete=ranking_complete,
        locale_supported=locale_supported,
    )
    return LogWindow(records=tuple(merged), coverage=coverage)


def _record_from_series(
    series: RawSeries,
    server_version_num: int,
    encodings: dict[str, str],
) -> LogRecord | None:
    parsed = parse_record(series.raw_record, server_version_num=server_version_num)
    if parsed is None or parsed.log_time is None:
        return None
    encoding = encodings.get(parsed.database_name or "", "utf-8")
    if encoding != "utf-8":
        reparsed = parse_record(
            series.raw_record, server_version_num=server_version_num, encoding=encoding
        )
        if reparsed is not None and reparsed.log_time is not None:
            parsed = reparsed
    raw_message = parsed.message or ""
    auto_explain_plan = parse_auto_explain(
        raw_message,
        complete=not (parsed.partial or series.raw_truncated),
    )
    message = sanitize_text(raw_message)
    # detail is internal evidence, already bounded by ScanRequest.raw_record_cap.
    # Keep it intact so item parsers can reach structured suffixes beyond the
    # display-oriented LINE_CAP used for messages.
    detail = sanitize_text(parsed.detail) if parsed.detail else None
    query = sanitize_text(parsed.query)[:LINE_CAP] if parsed.query else None
    context = sanitize_text(parsed.context)[:LINE_CAP] if parsed.context else None
    application_name = (
        sanitize_text(parsed.application_name)[:256] if parsed.application_name else None
    )
    last_time = parse_timestamp(series.last_ts) or parsed.log_time
    return LogRecord(
        log_time=parsed.log_time,
        last_time=last_time,
        repeat_count=series.count,
        severity=parsed.severity or "UNKNOWN",
        sql_state=parsed.sql_state,
        message=message[:LINE_CAP],
        user_name=parsed.user_name,
        database_name=parsed.database_name,
        process_id=parsed.process_id,
        connection_from=parsed.connection_from,
        backend_type=parsed.backend_type,
        query_id=parsed.query_id,
        partial=parsed.partial or series.raw_truncated,
        count_complete=True,
        encoding_degraded=parsed.encoding_degraded,
        fingerprint=fingerprint(message),
        detail=detail,
        auto_explain_plan=auto_explain_plan,
        session_id=parsed.session_id[:128] if parsed.session_id else None,
        session_line_num=parsed.session_line_num,
        command_tag=parsed.command_tag[:128] if parsed.command_tag else None,
        session_start_time=parsed.session_start_time,
        transaction_id=parsed.transaction_id,
        application_name=application_name,
        query=query,
        context=context,
        message_full=message,
    )


def _merge_records(head: LogRecord, nxt: LogRecord) -> LogRecord:
    return replace(
        head,
        last_time=max(head.last_time, nxt.last_time),
        repeat_count=head.repeat_count + nxt.repeat_count,
        partial=head.partial or nxt.partial,
        count_complete=head.count_complete and nxt.count_complete,
        encoding_degraded=head.encoding_degraded or nxt.encoding_degraded,
    )


def _can_merge_client_records(head: LogRecord, nxt: LogRecord) -> bool:
    """Keep numeric resource metrics and event timestamps intact.

    Generic fingerprints deliberately normalize numbers for flood grouping.
    For resource and lock-wait events those numbers carry sizes, durations,
    waiters and targets; merging would retain only the first event's values.
    WAL record lengths also determine whether a message indicates corruption.
    """
    preserve_event_time = (
        "57014",
        "55P03",
        "57P01",
    )
    return not (
        head.message.startswith(("duration:", "temporary file:", "invalid record length"))
        or nxt.message.startswith(("duration:", "temporary file:", "invalid record length"))
        or head.auto_explain_plan is not None
        or nxt.auto_explain_plan is not None
        or head.sql_state in preserve_event_time
        or nxt.sql_state in preserve_event_time
        or "conflict with recovery" in head.message.lower()
        or "conflict with recovery" in nxt.message.lower()
        or _LOCK_WAIT_EVENT_RE.match(head.message)
        or _LOCK_WAIT_EVENT_RE.match(nxt.message)
    )
