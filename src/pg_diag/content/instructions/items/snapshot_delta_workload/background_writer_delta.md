# Background Writer Delta

This instruction belongs to report item `snapshot_delta_workload.background_writer_delta`.

## What this item shows
- Buffers cleaned, allocation activity, cleaning-limit stops, and version-dependent backend writes/fsyncs.

## What to watch
- Repeated `maxwritten_clean` increases and, on PostgreSQL 10-16, backend fsync activity.

## Automatic evaluation
- New backend fsync operations produce `medium` severity on versions exposing that counter.

## Interval coverage
- Values require unchanged `pg_stat_bgwriter.stats_reset`.
- Unsupported backend-write counters remain null and carry a column status on PostgreSQL 17 and newer.

## Common fault causes
- Sustained dirty-buffer pressure, ineffective background cleaning, checkpoint pressure, and slow storage.

## Related report items
- [snapshot_delta_workload.checkpointer_delta](#item-snapshot_delta_workload.checkpointer_delta) — Separate background-writer and checkpointer activity.
- [snapshot_delta_workload.postgresql_io_delta](#item-snapshot_delta_workload.postgresql_io_delta) — Inspect associated PostgreSQL I/O contexts.
- [snapshot_charts_os.os_disk_latency](#item-snapshot_charts_os.os_disk_latency) — Check host write latency.

## Checklist
- Correlate with Checkpointer Delta, PostgreSQL I/O Delta, WAL, and disk latency.
- Do not interpret an unsupported null as observed zero activity.
