# Top SQL By Total Time

This instruction belongs to report item `sql_workload.top_sql_by_total_time`. The item is backed by `statements.top_by_total_time` (SQL query).

## What this item shows
- Statements ranked by cumulative execution time.
- Total, mean, max, and plan time plus rows, block, temp, and WAL counters for each normalized statement.
- Which SQL consumes most database execution time overall.

## What to watch
- One normalized query dominating total time.
- High total time with high calls, indicating a common slow path.
- High total time with low calls, indicating expensive reports or batch queries.

## Common fault causes
- Missing index or poor join order.
- Stale statistics.
- High call frequency from application path.
- Expensive reporting query.

## Checklist
- Tune the largest total-time contributors first.
- Compare calls, mean time, and max time before choosing action.
- Capture EXPLAIN ANALYZE for representative parameters.
