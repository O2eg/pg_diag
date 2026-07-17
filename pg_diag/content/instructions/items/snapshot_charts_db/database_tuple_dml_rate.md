# Database Tuple DML Rate

This instruction belongs to report item `snapshot_charts_db.database_tuple_dml_rate`. The item is backed by `database.tuple_dml_rate` (snapshot metric).

## What this item shows
- Insert, update, and delete rates for every named database.
- Current row-change workload intensity.

## Units
- `rows/s` means insert, update, or delete counter increments per wall-clock second. It measures PostgreSQL row-change events, not the number of distinct rows affected.

## What to watch
- Update/delete spikes.
- Low HOT update share on update-heavy workload.
- Unexpected DML outside business window.

## Common fault causes
- Batch writes.
- Purge job.
- Application release change.
- Index set preventing HOT updates.

## Automatic evaluation
- Insert, update, and delete counter deltas are stacked and partitioned by database.
- Counter decreases after reset become missing points; no workload-independent rate threshold is assigned.

## Related report items
- [snapshot_delta_workload.table_dml_delta](#item-snapshot_delta_workload.table_dml_delta) — Attribute database DML to tables.
- [snapshot_charts_db.wal_growth_rate](#item-snapshot_charts_db.wal_growth_rate) — Check WAL amplification from write activity.
- [storage_vacuum.autovacuum_queue](#item-storage_vacuum.autovacuum_queue) — Check maintenance pressure after DML.

## Checklist
- Compare with table_dml_delta.
- Check WAL growth for write amplification.
- Review hot tables and autovacuum pressure.
