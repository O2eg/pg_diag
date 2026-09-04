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
    "server_log.deadlock_events": compile_clauses([[",40P01,"]]),
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
    "server_log.lock_waits": compile_clauses(
        [
            [",LOG,00000,", "process ", " still waiting for ", " after "],
            [",LOG,00000,", "process ", " acquired ", " after "],
        ]
    ),
    "server_log.auto_explain_plans": compile_clauses([["duration: ", " ms  plan:"]]),
    "server_log.wraparound_pressure": compile_clauses(
        [
            ["must be vacuumed within"],
            ["is not accepting commands"],
        ]
    ),
    "server_log.system_incidents": compile_clauses(
        [
            [",53100,"], [",53200,"], [",53300,"], [",53400,"],
            [",58000,"], [",58030,"], [",58P01,"], [",58P02,"],
            [",XX001,"], [",XX002,"],
            ["No space left on device"], ["out of memory"],
            ["could not fsync"], ["could not write"], ["could not read"],
            ["checksum failure"], ["incorrect checksum"],
            ["invalid page in block"], ["invalid record length"],
        ]
    ),
    "server_log.server_lifecycle": compile_clauses(
        [
            ["database system is ready to accept"], ["database system is shut down"],
            ["shutdown request"], ["starting PostgreSQL"],
            ["was not properly shut down"], ["automatic recovery in progress"],
            ["redo starts at"], ["redo done at"], ["timeline ID"],
            ["invalid record length"],
            ["promote request"], ["reloading configuration files"],
            ["configuration file contains errors"], ["terminated by signal"],
            ["terminating any other active server processes"], ["could not bind"],
            ["could not create any TCP/IP sockets"],
        ]
    ),
    "server_log.replication_events": compile_clauses(
        [
            ["archive command failed"], ["restore command failed"],
            ["requested WAL segment"], ["has already been removed"],
            ["could not receive data from WAL stream"], ["terminating walreceiver"],
            ["could not send data to client"], ["could not receive data from client"],
            ["requested starting point"],
            ["not in this server"], ["requested timeline"], ["replication slot"],
            ["logical replication"], ["subscription"], ["conflict with recovery"],
        ]
    ),
    "server_log.query_termination_events": compile_clauses(
        [[",57014,"], [",55P03,"], [",57P01,"], ["conflict with recovery"]]
    ),
    "server_log.query_resource_events": compile_clauses(
        [
            ["duration: ", " ms  statement:"],
            ["duration: ", " ms  execute "],
            ["temporary file:", "size "],
        ]
    ),
    "server_log.maintenance_events": compile_clauses(
        [
            ["automatic vacuum of table"], ["automatic analyze of table"],
            [",VACUUM,"], [",ANALYZE,"], [",REINDEX,"],
            ["autovacuum", "canceling"], ["to prevent wraparound"],
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
