# PostgreSQL I/O Delta

This instruction belongs to report item `snapshot_delta_workload.postgresql_io_delta`.

## What this item shows
- Cluster I/O performed during the window, grouped by backend type, object, and I/O context.
- Reads, writes, extensions, writebacks, fsyncs, cache events, bytes, and timing where enabled.

## What to watch
- Client-backend writes or fsyncs, high eviction counts, and heavy bulk or vacuum I/O competing with foreground work.
- Timing columns remain zero when the corresponding PostgreSQL timing setting is disabled.

## Automatic evaluation
- No severity is assigned because expected I/O differs by backend type and workload phase.

## Interval coverage
- Available on PostgreSQL 16 and newer; rows require unchanged `pg_stat_io.stats_reset` and matching dimensions.

## Common fault causes
- Checkpoint pressure, insufficient cache, bulk scans, COPY, autovacuum, temporary relations, and slow storage.

## Checklist
- Compare byte rates with OS disk throughput and latency.
- Verify `track_io_timing` and `track_wal_io_timing` before interpreting zero timing values.
