# Statistics Reset Times

This instruction belongs to report item `overview.stat_reset_times`. The item is backed by `cluster.stat_reset_times` (SQL query).

## What this item shows
- Reset timestamps for PostgreSQL statistics views that expose `stats_reset`.
- Elapsed time since each reset in seconds and a compact text form.
- `reset_status`, so an empty timestamp is explicit instead of looking like a rendering problem.
- Separate rows for database-level, cluster-level, WAL, SLRU, I/O, recovery prefetch, and replication slot statistics when the PostgreSQL version exposes them.
- SLRU rows are separate because `pg_stat_reset_slru(target)` can reset one SLRU area without resetting the others.

## What to watch
- Very recent resets before interpreting cumulative counters in the report.
- Different reset ages between `pg_stat_database`, WAL, I/O, and SLRU statistics.
- Rows with `reset_status = not_reported`, which mean that the source did not report a reset time.

## Common fault causes
- Manual calls to reset functions such as `pg_stat_reset()`, `pg_stat_reset_shared()`, or object-specific reset functions.
- PostgreSQL restart or statistics subsystem reset.
- Maintenance, testing, or monitoring jobs that reset counters before a diagnostic capture.

## Automatic evaluation
- Reset age is not assigned a severity because planned resets and cluster age vary by environment.
- `not_reported` means the view returned no timestamp; it is not converted to a pass, failure, or zero age.
- pg_diag only reads these timestamps and never invokes statistics reset functions.

## Related report items
- [overview.database_stats](#item-overview.database_stats) — Interpret cumulative database counters against their reset epoch.
- [object_workload.table_workload](#item-object_workload.table_workload) — Interpret cumulative table counters against reset history.
- [object_workload.index_workload](#item-object_workload.index_workload) — Interpret cumulative index counters against reset history.

## Checklist
- Check this item before relying on cumulative totals in database, WAL, table, index, and function workload sections.
- Prefer snapshot delta items when a reset happened shortly before or during the capture window.
- Treat object-level workload totals carefully: table, index, and function stats can be reset independently, but PostgreSQL does not expose per-object reset timestamps in those views.
