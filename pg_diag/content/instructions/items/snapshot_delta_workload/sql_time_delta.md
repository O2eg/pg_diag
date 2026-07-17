# SQL Time Delta

This instruction belongs to report item `snapshot_delta_workload.sql_time_delta`. The item is backed by `statements.total_time_delta` (snapshot metric).

## What this item shows
- Calls, rows, execution-time delta, and execution milliseconds per wall-clock second for statement entries present at both endpoints.
- `(dbid, userid, queryid)` identity plus `toplevel` where PostgreSQL exposes it; the title names the only database in scope and the table retains the role label.
- A bounded candidate set: each endpoint keeps the 50 entries with highest cumulative execution time before backend loading.

## What to watch
- High `exec_time_ms_per_sec` and call rate for an incident-window statement.
- Values above 1000 ms/s, which are possible with concurrent executions and are not CPU percentage.
- Different Top-N membership between endpoints or unavailable cross-user query IDs.

## Automatic evaluation
- No severity is assigned because execution-time budgets differ by workload and concurrency.
- SQL identity-hidden rows are excluded by the source because they cannot form a safe delta key.

## Interval coverage
- Global `pg_stat_statements_info.stats_reset` is checked on PostgreSQL 14-18; PostgreSQL 10-13 does not expose this view. PostgreSQL 17+ also checks per-entry `stats_since`.
- `epoch_changed` or a counter decrease is invalid coverage and is omitted.
- `missing_start`/`missing_end` is expected bounded-selection churn, not zero activity. On PostgreSQL 10-16 entry eviction has no per-entry epoch and may only appear as churn or a decrease.

## Common fault causes
- Incident workload differs from historical Top SQL, a batch burst, waits inside statement execution, or external pg_stat_statements reset/eviction.

## Related report items
- [sql_workload.top_sql_by_total_time](#item-sql_workload.top_sql_by_total_time) — Compare incident-window SQL with cumulative Top SQL.
- [snapshot_delta_workload.sql_io_delta](#item-snapshot_delta_workload.sql_io_delta) — Check shared-block work for the same statement identity.
- [snapshot_delta_workload.sql_wal_delta](#item-snapshot_delta_workload.sql_wal_delta) — Check WAL generation for the same statement identity.

## Checklist
- Correlate the four-part identity with cumulative Top SQL and wait evidence.
- Account for Top-50 candidate selection before claiming a global incident-window ranking.
- Run representative plan analysis only when executing the statement is safe.
- Empty means no non-zero comparable entry; `unsupported` normally means pg_stat_statements is unavailable or outdated.
