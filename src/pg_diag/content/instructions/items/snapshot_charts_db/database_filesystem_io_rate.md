# Database Filesystem I/O Rate

This instruction belongs to report item `snapshot_charts_db.database_filesystem_io_rate`. The item is backed by `database.filesystem_io_rate` (snapshot metric).

## What this item shows
- Database-level execution reads and writes from `pg_stat_kcache` as a repeated line chart.
- `B/s` means filesystem-counter bytes per wall-clock second; it is not shared-buffer block throughput and need not equal physical-device throughput.
- Top-level entries are aggregated to avoid nested-statement double counting.

## What to watch
- Read/write bursts aligned with OS device throughput, utilization, queueing, or latency.
- Database I/O without matching PostgreSQL block rates, or device traffic not attributed to SQL execution.
- Counter gaps caused by reset or aggregation membership churn.

## Automatic evaluation
- No throughput threshold is assigned because filesystem and storage capacity are deployment-specific.
- Optional native counters are omitted when the platform does not expose them.

## Common fault causes
- Cold cache, large scans, temporary files, relation extension, or extension filesystem access.
- Checkpoint/background activity visible at the OS layer but not attributed to statement execution.
- Different kernel, cache, filesystem, and device accounting layers.

## Related report items
- [snapshot_delta_workload.sql_filesystem_io_delta](#item-snapshot_delta_workload.sql_filesystem_io_delta) — Attribute a database burst to SQL.
- [snapshot_delta_workload.sql_io_attribution_delta](#item-snapshot_delta_workload.sql_io_attribution_delta) — Compare filesystem bytes with PostgreSQL blocks.
- [snapshot_charts_os.os_disk_read_throughput](#item-snapshot_charts_os.os_disk_read_throughput) — Compare reads with devices.
- [snapshot_charts_os.os_disk_write_throughput](#item-snapshot_charts_os.os_disk_write_throughput) — Compare writes with devices.

## Checklist
- Align chart intervals before comparing counters from different layers.
- Separate statement execution I/O from checkpointer, WAL, and other processes.
- Use OS latency/utilization to decide whether throughput is harmful.
- Empty means fewer than two comparable samples or no native I/O delta; `unsupported` normally means pg_stat_kcache 2.3+ is unavailable.
