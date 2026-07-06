# PostgreSQL I/O Statistics

This instruction belongs to report item `wal_io_checkpoints.pg_stat_io`. The item is backed by `io.pg_stat_io` (SQL query).

## What this item shows
- pg_stat_io counters grouped by backend type, object, context, and operation.
- PostgreSQL internal I/O patterns such as relation, temp, WAL, and vacuum-related I/O.
- Which backend types are driving reads, writes, extends, fsyncs, or evictions.

## What to watch
- Client backend writes dominating background writes.
- High fsync or write time in one context.
- Vacuum or autovacuum I/O during workload peaks.
- Temp I/O context activity.

## Common fault causes
- Write bursts.
- Slow storage.
- Autovacuum or maintenance activity.
- Temp spills.
- Insufficient caching for working set.

## Checklist
- Group by backend_type and context before acting.
- Compare with OS disk latency and throughput charts.
- Trace high relation I/O to SQL and object workload sections.
