# WAL Statistics

This instruction belongs to report item `wal_io_checkpoints.wal_statistics`. The item is backed by `wal.stat_wal` (SQL query).

## What this item shows
- Cluster-wide cumulative WAL records, full-page images, bytes, buffer-full events, average bytes/record, and reset age.
- PostgreSQL 14-17 WAL write/sync counts and timing. PostgreSQL 18 moved WAL operation I/O to `pg_stat_io`, so those columns are not fabricated here.
- Whether `track_wal_io_timing` is enabled for timing interpretation.

## What to watch
- Increases in WAL bytes, FPIs, or `wal_buffers_full` relative to elapsed time and workload.
- WAL write/sync time when timing is enabled, and archive/replication capacity.

## Automatic evaluation
- No automatic severity: cumulative volume and buffer-full counts need rates, reset age, workload, and service objectives.

## Common fault causes
- Write-heavy or small-transaction workload, bulk loads, full-page images after checkpoints, logical WAL level, or undersized WAL buffers during bursts.

## Related report items
- [snapshot_delta_workload.wal_activity_delta](#item-snapshot_delta_workload.wal_activity_delta) — Measure WAL counter changes in the capture window.
- [sql_workload.top_sql_by_wal](#item-sql_workload.top_sql_by_wal) — Attribute cumulative WAL to statements.
- [wal_io_checkpoints.checkpointer](#item-wal_io_checkpoints.checkpointer) — Check checkpoint activity associated with WAL.

## Checklist
- Calculate deltas using the same reset epoch; do not compare raw totals across resets.
- Use WAL growth and Top SQL by WAL for rates and attribution.
- On PostgreSQL 18 inspect WAL rows in `pg_stat_io` for write/fsync activity.
- Do not reset shared counters during diagnosis.
