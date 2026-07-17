# Database I/O Time Rate

This instruction belongs to report item `snapshot_charts_db.database_io_time_rate`. The item is backed by `database.io_time_rate` (snapshot metric).

## What this item shows
- Rate of read and write time accumulation from database statistics.
- Time PostgreSQL reports spending in database I/O.

## What to watch
- I/O time rising faster than throughput.
- Write time spikes during checkpoints.
- Read time spikes during query latency.

## Common fault causes
- Slow storage.
- Queueing.
- Large reads/writes.
- Checkpoint or WAL pressure.

## Automatic evaluation
- `ms/s` is accumulated backend time per wall-clock second and can exceed 1000 under concurrent I/O.
- With `track_io_timing=off`, zero counters mean unavailable timing rather than proven absence of I/O waits.

## Related report items
- [wal_io_checkpoints.pg_stat_io](#item-wal_io_checkpoints.pg_stat_io) — Inspect PostgreSQL I/O time by backend and context.
- [snapshot_charts_os.os_disk_latency](#item-snapshot_charts_os.os_disk_latency) — Compare accumulated backend time with device latency.
- [snapshot_charts_db.io_read_write_rate](#item-snapshot_charts_db.io_read_write_rate) — Compare I/O time with byte throughput.

## Checklist
- Compare with pg_stat_io and OS latency.
- Separate read-time and write-time symptoms.
- Confirm track_io_timing availability.
