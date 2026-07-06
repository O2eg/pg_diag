# Top SQL By Temp I/O

This instruction belongs to report item `sql_workload.top_sql_by_temp_io`. The item is backed by `statements.top_by_temp_io` (SQL query).

## What this item shows
- Statements ranked by temporary block usage.
- SQL that spills sort, hash, materialize, or aggregate work to temp files.
- Temp block pressure attributable to normalized statements.

## What to watch
- High temp blocks on OLTP queries.
- Recurring spills from the same query_id.
- Spills during periods of disk latency or full temp filesystem.

## Common fault causes
- work_mem too low for query shape.
- Large sort or hash join.
- Missing index that forces sort/hash work.
- Large GROUP BY or DISTINCT.

## Checklist
- Inspect EXPLAIN ANALYZE for Sort Method and Hash batches.
- Tune query/indexes before raising work_mem globally.
- Check temp filesystem capacity and latency.
