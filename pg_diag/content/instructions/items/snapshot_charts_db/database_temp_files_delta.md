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

## Automatic evaluation
- Columns show newly created temp files per adjacent interval, not a rate.
- Counter reset produces a missing interval; a file count alone does not reveal spill size.

## Related report items
- [sql_workload.top_sql_by_temp_io](#item-sql_workload.top_sql_by_temp_io) — Identify statements with cumulative temporary I/O.
- [snapshot_delta_workload.sql_temp_io_delta](#item-snapshot_delta_workload.sql_temp_io_delta) — Measure statement spills in the capture window.
- [snapshot_charts_db.database_temp_bytes_rate](#item-snapshot_charts_db.database_temp_bytes_rate) — Compare file count with spill volume.

## Checklist
- Compare with Top SQL by Temp I/O.
- Inspect EXPLAIN ANALYZE spill details.
- Check temp filesystem capacity.
