# Top SQL By Mean Time

This instruction belongs to report item `sql_workload.top_sql_by_mean_time`. The item is backed by `statements.top_by_mean_time` (SQL query).

## What this item shows
- Statements ranked by average execution time per call.
- Mean and max latency candidates that may be hidden in total-time ranking.
- Rare but expensive normalized SQL patterns.

## What to watch
- High mean time with low calls.
- High max time much larger than mean time.
- Queries with small row count but high execution time.

## Common fault causes
- Parameter-sensitive plan.
- Occasional report or maintenance query.
- Lock waits included in execution time.
- Cold cache or stale statistics.

## Checklist
- Check calls before prioritizing a rare statement.
- Compare mean, max, and total time.
- Test representative parameter sets with EXPLAIN ANALYZE.
