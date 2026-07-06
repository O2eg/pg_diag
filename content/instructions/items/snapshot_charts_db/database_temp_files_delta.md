# Database Temp Files Delta

This instruction belongs to report item `snapshot_charts_db.database_temp_files_delta`. The item is backed by `database.temp_files_delta` (snapshot metric).

## What this item shows
- Temporary file count delta over time.
- Rate of temp file creation during snapshots.

## What to watch
- Temp file bursts.
- Temp files created during specific SQL spikes.
- Unexpected temp activity on OLTP workload.

## Common fault causes
- Sort/hash spill.
- Large materialization.
- work_mem too low for query shape.

## Checklist
- Compare with Top SQL by Temp I/O.
- Inspect EXPLAIN ANALYZE spill details.
- Check temp filesystem capacity.
