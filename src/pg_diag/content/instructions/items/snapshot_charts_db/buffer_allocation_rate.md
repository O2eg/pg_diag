# Buffer Allocation And Cleaning Rate

This instruction belongs to report item `snapshot_charts_db.buffer_allocation_rate`. The item is backed by `checkpoints.buffer_allocation_rate` (snapshot metric).

## What this item shows
- Shared-buffer allocations per second (`buffers_alloc`): turnover/demand for shared buffer slots, including allocations that do not require a physical read.
- Buffers cleaned per second by the background writer (`buffers_clean`).
- Cluster-wide counters from `pg_stat_bgwriter` on every supported PostgreSQL major.

## What to watch
- Sustained allocation turnover together with physical reads or evictions; that combination is stronger evidence of cache pressure than allocations alone.
- Cleaning far below allocation while backends write their own buffers in Buffer Writes By Process. The rates are not expected to match because an allocated slot can replace a clean buffer.
- Cleaning flat at a ceiling together with stops in Writer Pressure Events.

## Common fault causes
- A working set larger than `shared_buffers`.
- Sequential scans over large tables.
- Bulk loads or relation extension, including new pages that were never cache misses.

## Automatic evaluation
- No severity is assigned: allocation volume depends on workload and cache size.
- A statistics reset produces a missing interval rather than zero.

## Related report items
- [snapshot_charts_db.buffer_writes_by_process](#item-snapshot_charts_db.buffer_writes_by_process) — Whether backends had to write buffers themselves.
- [snapshot_charts_db.writer_pressure_events](#item-snapshot_charts_db.writer_pressure_events) — Background-writer stops in the same window.
- [snapshot_charts_db.database_block_access_rate](#item-snapshot_charts_db.database_block_access_rate) — Block hits and reads per database.
- [snapshot_delta_workload.background_writer_delta](#item-snapshot_delta_workload.background_writer_delta) — Window totals for the same counters.

## Checklist
- Compare allocation with block reads and, on PostgreSQL 16 and newer, `pg_stat_io` evictions before concluding that the cache is under pressure.
- Review `shared_buffers` against the working set before tuning the background writer.
- Check bulk jobs before reading a high allocation rate as a fault.
