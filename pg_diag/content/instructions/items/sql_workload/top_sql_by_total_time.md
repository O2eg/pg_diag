# Top SQL By Total Time

This instruction belongs to report item `sql_workload.top_sql_by_total_time`. The item is backed by `statements.top_by_total_time` (SQL query).

## What this item shows
- Up to 50 current-database entries ranked by cumulative execution time, not by activity during the pg_diag capture window.
- Full entry identity: database OID, user OID, query ID, and `toplevel`, plus the role label and representative SQL text; the database name is carried by the item title.
- Calls, mean/max execution time, planning time, rows, shared/temp blocks, I/O timing, and WAL counters. PostgreSQL 17+ adds entry/min-max start timestamps; PostgreSQL 18 adds parallel-worker launch counters.

## What to watch
- High total time combined with many calls, or expensive low-frequency batch/report statements.
- `toplevel = false`, which identifies nested statements tracked from functions or procedures when `track = all`.
- Planning counters at zero when planning tracking is off, and I/O timings at zero when `track_io_timing` is off.
- Entry age/reset and deallocation churn before comparing cumulative totals.

## Automatic evaluation
- Workload values do not assign severity because acceptable time and frequency are workload-specific.
- `unknown` means at least one returned row has hidden query identity. Its counters are real, but it cannot be safely attributed to normalized SQL.
- The table is one-shot and bounded before backend loading. It is not a complete history, an interval delta, or a global Top 50 across databases.

## Common fault causes
- Missing indexes, poor join order, stale statistics, or parameter-sensitive plans.
- A high-frequency application path, long lock/I/O waits, or legitimate analytical work.
- Entry eviction caused by insufficient `pg_stat_statements.max`.

## Checklist
- Check capability, visibility, `stats_reset`, and entry age first.
- Compare calls, mean/max time, rows, I/O, and WAL before choosing a tuning target.
- Capture a representative plan under safe production procedures; `EXPLAIN ANALYZE` executes the statement.
- Empty means no visible current-database entries at collection time; `unsupported` usually means the extension view is absent.
