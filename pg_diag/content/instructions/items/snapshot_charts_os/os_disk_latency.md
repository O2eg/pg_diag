# Disk Latency

This instruction belongs to report item `snapshot_charts_os.os_disk_latency`. The item is backed by `os.disk_latency` (snapshot metric).

## What this item shows
- Read and write latency by device over time.
- Storage response time during the capture window.

## Units
- `ms` means average milliseconds per completed I/O request during the interval. The iostat `await`, read-await, and write-await values include time spent queued and serviced by the device stack.

## What to watch
- Latency spikes on WAL or data device.
- Sustained high write latency during checkpoints.
- Read latency aligned with query slowdown.

## Common fault causes
- Slow storage.
- Queueing from high IOPS.
- Checkpoint or WAL sync pressure.
- Shared storage contention.

## Automatic evaluation
- `await` is the combined average and read/write await are separate line series; they are not added.
- No fixed severity is assigned because latency targets depend on device and workload.

## Related report items
- [snapshot_charts_os.os_disk_utilization](#item-snapshot_charts_os.os_disk_utilization) — Check whether latency accompanies sustained busy time.
- [wal_io_checkpoints.pg_stat_io](#item-wal_io_checkpoints.pg_stat_io) — Attribute PostgreSQL I/O by backend and context.
- [snapshot_delta_workload.sql_io_delta](#item-snapshot_delta_workload.sql_io_delta) — Identify statements doing shared-block I/O.

## Checklist
- Map device to WAL/data/archive paths.
- Compare with checkpointer, WAL, and pg_stat_io.
- Investigate storage before changing query plans when latency dominates.
