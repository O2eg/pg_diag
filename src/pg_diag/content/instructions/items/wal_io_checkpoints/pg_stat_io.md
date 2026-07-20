# PostgreSQL I/O Statistics

This instruction belongs to report item `wal_io_checkpoints.pg_stat_io`. The item is backed by `io.pg_stat_io` (SQL query).

## What this item shows
- PostgreSQL 16+ cluster-wide cumulative I/O grouped by the real `backend_type`, `object`, and `context` dimensions without a duplicate total rollup.
- Exact byte and operation counters, timing, hits, evictions, reuses, fsyncs, writebacks, extends, reset age, and timing settings. Byte values are collected as bytes and rendered with adaptive IEC units.
- PostgreSQL 18 uses direct byte counters and adds WAL-object rows; it exposes no writeback-byte count, so `writeback_bytes` is null with an unsupported column status rather than zero.

## What to watch
- Relation fsyncs by client backends, client relation writes displacing background work, high eviction/read deltas, or slow operation times.
- WAL rows separately from relation/temp-relation rows on PostgreSQL 18.
- Timing columns only when the matching tracking setting is enabled.

## Automatic evaluation
- `medium`: a `client backend` has relation-object fsyncs since the I/O reset.
- Client WAL fsyncs are normal commit-path activity and do not trigger this finding.
- Other volumes and timing values remain contextual.

## Common fault causes
- Checkpointer pressure, insufficient shared-buffer reuse, bulk I/O, vacuum, temp relations, write bursts, or slow storage.
- A kernel page-cache hit can still appear as a PostgreSQL read operation; this view does not prove physical disk access.

## Related report items
- [snapshot_delta_workload.postgresql_io_delta](#item-snapshot_delta_workload.postgresql_io_delta) — Measure I/O counter changes in the capture window.
- [snapshot_charts_os.os_disk_latency](#item-snapshot_charts_os.os_disk_latency) — Correlate PostgreSQL I/O with host latency.
- [sql_workload.top_sql_by_shared_io](#item-sql_workload.top_sql_by_shared_io) — Identify statements with high shared-block activity.

## Checklist
- Compare deltas for the same backend/object/context and reset epoch.
- Correlate with OS disk latency/throughput and SQL/object workload.
- Do not add backend-type rows together with a synthetic total; this item intentionally emits no total row.
- Unsupported on PostgreSQL 10-15.
