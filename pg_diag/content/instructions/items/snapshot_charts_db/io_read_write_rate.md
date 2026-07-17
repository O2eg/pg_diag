# I/O Read And Write Rate

This instruction belongs to report item `snapshot_charts_db.io_read_write_rate`. The item is backed by `io.read_write_rate` (snapshot metric).

## What this item shows
- PostgreSQL read and write byte rates by backend type from pg_stat_io.
- Cluster-wide PostgreSQL I/O rate over the capture window.

## Units
- `B/s` means bytes read or written per wall-clock second. The chart uses adaptive IEC rate units such as `KiB/s`, `MiB/s`, or `GiB/s`.

## What to watch
- Client backend reads or writes dominating.
- Autovacuum or checkpointer I/O spikes.
- I/O rate aligned with OS disk saturation.

## Common fault causes
- Large scans.
- Bulk writes.
- Vacuum.
- Checkpoint activity.
- Temp spill.

## Automatic evaluation
- Backend-type rows are stacked without a separate total rollup, preventing double counting.
- PostgreSQL 16-17 derives bytes from operation counts and `op_bytes`; PostgreSQL 18+ uses byte counters directly.
- Counter resets become missing points; the chart is unavailable before PostgreSQL 16.

## Checklist
- Group by backend type before tuning.
- Compare with OS disk throughput and latency.
- Trace high relation I/O to SQL and object sections.
