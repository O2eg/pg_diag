# Copy Progress

This instruction belongs to report item `maintenance_progress.copy_progress`. The item is backed by `progress.copy` (SQL query).

## What this item shows
- A one-time, current-database snapshot of COPY FROM/TO operations visible when the report starts.
- Command and I/O type, database/relation OIDs and name, state/wait, processed/total bytes, tuple counts, command age, and bounded query text.
- `relid=0`/null relation for COPY from a query; `bytes_total=0` means PostgreSQL cannot provide a source size, so percentage is null.
- PostgreSQL 17+ malformed-row `tuples_skipped` when the server exposes it; older versions return null.

## What to watch
- Repeated captures with no byte/tuple movement, client/network waits, or overlap with WAL, archive, replication, and storage pressure.
- COPY FROM constraint/index overhead and COPY TO client backpressure.

## Automatic evaluation
- No automatic severity: COPY duration and throughput depend on source type, transformation, constraints, client behavior, and hardware.
- AccessExclusiveLock presence no longer hides a COPY row; the query also avoids `pg_relation_size()` so observing progress does not wait on that lock.

## Common fault causes
- Slow FILE/PROGRAM/PIPE/CALLBACK source or sink, network backpressure, index/constraint work, WAL/archive saturation, malformed input, or storage latency.

## Checklist
- Compare later captures by PID and command; calculate throughput only from real deltas and elapsed time.
- Inspect wait events, client path, WAL/archive capacity, relation indexes, and error logs before intervention.
- Treat skipped/excluded tuples according to the COPY options and data-quality policy.
- Empty means no visible current-database COPY was active at capture time.
