from __future__ import annotations

from typing import Any

from pg_diag.executors.python import PythonSourceContext, PythonSourceResult, table_result
from pg_diag.logscan.items_common import (
    coverage_note,
    empty_result_status,
    fmt_time,
    is_recovery_end_of_wal,
    resolve_window,
    severity_rank,
)

ROW_LIMIT = 100

_SQLSTATE_KIND = {
    "53100": "disk_full",
    "53200": "out_of_memory",
    "53300": "too_many_connections",
    "53400": "configuration_limit",
    "58000": "system_error",
    "58030": "io_error",
    "58P01": "missing_file",
    "58P02": "duplicate_file",
    "XX001": "data_corruption",
    "XX002": "index_corruption",
}
_MESSAGE_KIND = (
    ("no space left on device", "disk_full"),
    ("out of memory", "out_of_memory"),
    ("cannot allocate memory", "out_of_memory"),
    ("too many connections", "too_many_connections"),
    ("remaining connection slots are reserved", "too_many_connections"),
    ("could not fsync", "fsync_failure"),
    ("could not write", "write_failure"),
    ("could not read", "read_failure"),
    ("checksum failure", "checksum_failure"),
    ("incorrect checksum", "checksum_failure"),
    ("invalid page in block", "data_corruption"),
    ("invalid record length", "wal_corruption"),
    ("invalid resource manager id", "wal_corruption"),
)


def collect(context: PythonSourceContext) -> PythonSourceResult:
    window, early = resolve_window(context)
    if early is not None:
        return PythonSourceResult(**early)

    candidates: list[tuple[Any, str]] = []
    for record in window.records:
        if is_recovery_end_of_wal(record):
            continue
        kind = _SQLSTATE_KIND.get(record.sql_state or "")
        if (
            kind is None
            and record.sql_state in (None, "", "00000", "XX000")
            and window.coverage.locale_supported
        ):
            message = record.message.lower().lstrip()
            kind = next(
                (value for fragment, value in _MESSAGE_KIND if message.startswith(fragment)),
                None,
            )
            # An OS errno follows a recognized server I/O message. Keep its
            # specific incident type without matching phrases in SQL identifiers.
            if kind in {"fsync_failure", "write_failure", "read_failure"}:
                if message.rstrip().endswith(": no space left on device"):
                    kind = "disk_full"
                elif message.rstrip().endswith(": cannot allocate memory"):
                    kind = "out_of_memory"
        if kind is not None:
            candidates.append((record, kind))

    ranked = sorted(
        candidates,
        key=lambda item: (
            severity_rank(item[0].severity),
            item[0].repeat_count,
            item[0].last_time,
        ),
        reverse=True,
    )
    omitted = max(0, len(ranked) - ROW_LIMIT)
    rows = [
        {
            "first_time": fmt_time(record.log_time),
            "last_time": fmt_time(record.last_time),
            "incident_type": kind,
            "severity": record.severity,
            "sql_state": record.sql_state,
            "occurrences": record.repeat_count,
            "database_name": record.database_name,
            "application_name": record.application_name,
            "backend_type": record.backend_type,
            "message": record.message,
            "count_complete": record.count_complete,
        }
        for record, kind in ranked[:ROW_LIMIT]
    ]
    result = table_result(rows)
    result.update(
        {
            "matched_series_count": len(candidates),
            "omitted_series_count": omitted,
            "row_limit": ROW_LIMIT,
            "message_pattern_coverage": (
                "full" if window.coverage.locale_supported else "structured_sqlstate_only"
            ),
        }
    )
    if not rows:
        if not window.coverage.locale_supported:
            return PythonSourceResult(
                collection_status="ok",
                result=result,
                severity_level="unknown",
                issues={
                    "summary": {
                        "severity": "unknown",
                        "status": "review",
                        "title": "No SQLSTATE incident found, but message coverage is partial",
                        "description": (
                            "lc_messages is not English. Stable SQLSTATE incidents were checked, "
                            "but message-only filesystem and corruption signatures could not be "
                            "classified, so absence is not proven."
                        ),
                        "recommendation": (
                            "Review localized ERROR/FATAL/PANIC chronology for message-only "
                            "storage and corruption evidence."
                        ),
                    },
                    "items": [],
                },
            )
        status, severity, issues = empty_result_status(window)
        return PythonSourceResult(
            collection_status=status,
            result=result,
            issues=issues,
            severity_level=severity,
        )

    note = coverage_note(window)
    locale_note = None
    if not window.coverage.locale_supported:
        locale_note = (
            "lc_messages is not English; SQLSTATE incidents are included, but message-only "
            "filesystem and corruption signatures cannot be classified."
        )
    details = [
        f"{len(candidates)} incident series matched; {len(rows)} are shown.",
        *(
            [f"{omitted} lower-ranked series were omitted by the fixed {ROW_LIMIT}-row limit."]
            if omitted
            else []
        ),
        *([locale_note] if locale_note else []),
        *([note] if note else []),
    ]
    severity = (
        "high"
        if any(record.severity in ("FATAL", "PANIC") for record, _ in candidates)
        else "medium"
    )
    return PythonSourceResult(
        collection_status="ok",
        result=result,
        severity_level=("unknown" if locale_note or note else severity),
        issues={
            "summary": {
                "severity": "unknown" if locale_note or note else severity,
                "status": "review",
                "title": "Server log contains system incidents",
                "description": " ".join(details),
                "recommendation": (
                    "Investigate storage, memory, connection capacity, and corruption evidence; "
                    "treat checksum, data, index, and WAL errors as incident-grade findings."
                ),
            },
            "items": [],
        },
    )
