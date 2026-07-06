# Table DML Delta

This instruction belongs to report item `snapshot_delta_workload.table_dml_delta`. The item is backed by `objects.table_dml_delta` (snapshot metric).

## What this item shows
- Per-table insert, update, delete, and HOT update deltas during the capture window.
- Current write hotspots by table.

## What to watch
- One table dominating DML.
- High update rate with low HOT update ratio.
- Unexpected deletes or inserts.

## Common fault causes
- Application hotspot.
- Batch job.
- Missing fillfactor or HOT-unfriendly indexes.
- Retention purge.

## Checklist
- Identify table owner and workload path.
- Check autovacuum pressure for hot tables.
- Compare with SQL WAL delta.
