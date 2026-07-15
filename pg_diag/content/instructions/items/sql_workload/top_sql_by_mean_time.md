# Top SQL By Mean Time

This instruction belongs to report item `sql_workload.top_sql_by_mean_time`. The item is backed by `statements.top_by_mean_time` (SQL query).

## What this item shows
- Up to 50 current-database entries ranked by cumulative mean execution time per completed call.
- Calls, total/mean/max execution time, rows, shared reads, temp blocks, WAL, full entry identity, and representative SQL.
- On PostgreSQL 17+, `stats_since` and `minmax_stats_since`; the max-time window can differ after a min/max-only reset.

## What to watch
- High mean time with enough calls to be representative.
- Max time far above mean, suggesting skew, waits, cache state, or plan sensitivity.
- Rare one-off statements at the top that have low total workload impact.

## Automatic evaluation
- Latency values do not assign severity because statement classes have different service-level objectives.
- `unknown` indicates hidden query identity for at least one row, normally due to cross-user visibility restrictions.
- Ranking is cumulative, one-shot, current-database-only, and limited to 50 rows before backend loading.

## Common fault causes
- Parameter-sensitive or stale plans, lock/I/O waits, cold cache, or expected analytical work.
- Too few calls for a stable average.
- A min/max-only reset making max and mean cover different periods on PostgreSQL 17+.

## Checklist
- Check calls, total time, `stats_since`, and `minmax_stats_since` before prioritizing a row.
- Test representative parameters and compare plan estimates with actual rows.
- Run `EXPLAIN ANALYZE` only when executing the statement is safe; use plain `EXPLAIN` otherwise.
- Empty or unsupported has the same extension/tracking interpretation as the capability item.
