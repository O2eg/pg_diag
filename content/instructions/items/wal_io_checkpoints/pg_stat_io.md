# PostgreSQL I/O Statistics

This instruction belongs to report item `wal_io_checkpoints.pg_stat_io`. The item is backed by `io.pg_stat_io` (SQL query).

## What this item shows
- PostgreSQL 16+ cluster-wide cumulative I/O grouped by the real `backend_type`, `object`, and `context` dimensions without a duplicate total rollup.
- Counts, MiB, timing, hits, evictions, reuses, fsyncs, writebacks, extends, reset age, and timing settings.
- PostgreSQL 18 uses direct byte counters and adds WAL-object rows; it exposes no writeback-byte count, so `writeback_bytes_mb` is null rather than zero.

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

## Checklist
- Compare deltas for the same backend/object/context and reset epoch.
- Correlate with OS disk latency/throughput and SQL/object workload.
- Do not add backend-type rows together with a synthetic total; this item intentionally emits no total row.
- Unsupported on PostgreSQL 14-15.
