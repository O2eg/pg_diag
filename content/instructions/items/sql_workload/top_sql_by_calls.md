# Top SQL By Calls

This instruction belongs to report item `sql_workload.top_sql_by_calls`. The item is backed by `statements.top_by_calls` (SQL query).

## What this item shows
- Statements ranked by execution count.
- High-frequency application paths and repeated SQL patterns.
- Whether lightweight queries are called excessively.

## What to watch
- Very high calls for lookup or health-check SQL.
- Repeated single-row statements that could be batched or cached.
- High calls combined with non-trivial mean time.

## Common fault causes
- N+1 query pattern.
- Missing application cache.
- Overly chatty health checks.
- Retry loop.

## Checklist
- Confirm high call volume is expected.
- Batch, cache, or remove low-value repeated calls.
- Prioritize high calls only when they also consume time, I/O, WAL, or connection capacity.
