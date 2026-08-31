"""Per-item recall clauses (plan §3, §15.7).

Each server_log item declares literal-substring clauses; the phase unions the
clauses of the items enabled in the current run, so a filtered run scans only
for what its items need and the log is still read exactly once.
"""

from __future__ import annotations

from .recall import RecallClauses, compile_clauses

_SEVERITY_ERRORS = [[",ERROR,"], [",FATAL,"], [",PANIC,"]]

ITEM_RECALL: dict[str, RecallClauses] = {
    "server_log.error_chronology": compile_clauses(_SEVERITY_ERRORS),
    "server_log.top_errors": compile_clauses(_SEVERITY_ERRORS),
    "server_log.top_warnings": compile_clauses([[",WARNING,"]]),
    "server_log.crash_recovery_events": compile_clauses(
        [
            ["terminated by signal"],
            ["was not properly shut down"],
            ["automatic recovery in progress"],
            ["redo starts at"],
            ["invalid page"],
            ["terminating any other active server processes"],
        ]
    ),
    "server_log.deadlock_events": compile_clauses([["deadlock detected"]]),
    "server_log.authentication_failures": compile_clauses(
        [
            ["password authentication failed"],
            ["no pg_hba.conf entry"],
            # SQLSTATE fields catch non-phrase variants (PAM, LDAP, RADIUS...)
            [",28000,"],
            [",28P01,"],
        ]
    ),
    "server_log.autovacuum_runs": compile_clauses(
        [
            ["automatic vacuum of table"],
            ["automatic analyze of table"],
        ]
    ),
    "server_log.checkpoints": compile_clauses(
        [
            ["checkpoint starting"],
            ["checkpoint complete"],
            ["restartpoint starting"],
            ["restartpoint complete"],
        ]
    ),
    "server_log.archiver_failures": compile_clauses([["archive command failed"]]),
    "server_log.wraparound_pressure": compile_clauses(
        [
            ["must be vacuumed within"],
            ["is not accepting commands"],
        ]
    ),
    # server_log.log_files_overview consumes the inventory only: no recall.
}


def clauses_for_items(item_ids: tuple[str, ...]) -> RecallClauses:
    merged: list[tuple[bytes, ...]] = []
    seen: set[tuple[bytes, ...]] = set()
    for item_id in item_ids:
        for clause in ITEM_RECALL.get(item_id, ()):
            if clause not in seen:
                seen.add(clause)
                merged.append(clause)
    return tuple(merged)
