# Database Temp Bytes Rate

This instruction belongs to report item `snapshot_charts_db.database_temp_bytes_rate`. The item is backed by `database.temp_bytes_rate` (snapshot metric).

## What this item shows
- Temporary bytes generated per second.
- Volume of spill data during snapshots.

## What to watch
- High temp byte rate.
- Temp bytes aligned with disk write latency.
- Repeated spill periods.

## Common fault causes
- Large sort/hash operations.
- Missing indexes.
- Large DISTINCT/GROUP BY.
- Insufficient work_mem for specific query.

## Automatic evaluation
- The chart derives bytes/second from cumulative temp bytes and partitions the result by database.
- Counter reset produces missing data; correlate with temp-file count and SQL temp I/O.

## Related report items
- [snapshot_delta_workload.sql_temp_io_delta](#item-snapshot_delta_workload.sql_temp_io_delta) — Attribute temp bytes to statements in the window.
- [snapshot_charts_db.database_temp_files_delta](#item-snapshot_charts_db.database_temp_files_delta) — Compare spill volume with file creation.
- [snapshot_charts_os.os_disk_latency](#item-snapshot_charts_os.os_disk_latency) — Check storage latency during spills.

## Checklist
- Find spilling SQL first.
- Tune query/indexes before global work_mem changes.
- Ensure temp storage can absorb bursts.
