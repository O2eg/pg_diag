# Database Tuple DML Rate

This instruction belongs to report item `snapshot_charts_db.database_tuple_dml_rate`. The item is backed by `database.tuple_dml_rate` (snapshot metric).

## What this item shows
- Insert, update, delete, and HOT update rates for the current database.
- Current row-change workload intensity.

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
- Insert, update, and delete counter deltas are stacked for the connected database.
- Counter decreases after reset become missing points; no workload-independent rate threshold is assigned.

## Checklist
- Compare with table_dml_delta.
- Check WAL growth for write amplification.
- Review hot tables and autovacuum pressure.
