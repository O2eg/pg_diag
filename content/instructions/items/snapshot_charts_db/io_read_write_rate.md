# I/O Read And Write Rate

This instruction belongs to report item `snapshot_charts_db.io_read_write_rate`. The item is backed by `io.read_write_rate` (snapshot metric).

## What this item shows
- PostgreSQL read and write byte rates by backend type from pg_stat_io.
- Database-side I/O rate over the capture window.

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

## Checklist
- Group by backend type before tuning.
- Compare with OS disk throughput and latency.
- Trace high relation I/O to SQL and object sections.
