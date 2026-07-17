# Table Maintenance Delta

This instruction belongs to report item `snapshot_delta_workload.table_maintenance_delta`.

## What this item shows
- Manual and automatic VACUUM/ANALYZE executions per table during the window.
- Maintenance timing on server versions that expose cumulative per-table duration counters.

## What to watch
- Repeated maintenance of the same table, long autovacuum time, or analyze activity that coincides with foreground pressure.

## Automatic evaluation
- No severity is assigned because maintenance frequency and duration depend on churn, table size, and configured thresholds.

## Interval coverage
- The source keeps the top 200 cumulative maintenance rows at each endpoint and returns the top 50 comparable deltas.
- Database statistics reset changes and endpoint Top-N churn are never treated as zero activity.

## Common fault causes
- High table churn, low scale factors, wraparound prevention, stale statistics, and expensive index cleanup.

## Related report items
- [storage_vacuum.autovacuum_queue](#item-storage_vacuum.autovacuum_queue) — Check queued tables and worker pressure.
- [snapshot_delta_workload.table_dml_delta](#item-snapshot_delta_workload.table_dml_delta) — Relate maintenance to table changes.
- [maintenance_progress.vacuum_progress](#item-maintenance_progress.vacuum_progress) — Inspect vacuum operations active now.

## Checklist
- Compare with autovacuum queue, dead tuples, table DML, WAL, and I/O evidence.
- On PostgreSQL 10-17, maintenance-time columns are null and marked unsupported; count deltas remain valid.
