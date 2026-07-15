# Top SQL By Temp I/O

This instruction belongs to report item `sql_workload.top_sql_by_temp_io`. The item is backed by `statements.top_by_temp_io` (SQL query).

## What this item shows
- Up to 50 current-database entries ranked by cumulative temporary blocks read plus written.
- Temp block counts and calculated I/O bytes, calls, execution time, rows, full identity, and representative SQL.
- `stats_since` on PostgreSQL 17+; on earlier versions the per-entry accumulation start is unavailable.

## What to watch
- Repeated temp I/O per call on latency-sensitive statements.
- Large cumulative totals during host disk pressure or temp-filesystem capacity incidents.
- A one-time analytical operation separated from a recurring OLTP spill.

## Automatic evaluation
- Temp I/O does not automatically assign severity because spill size and applicability depend on query class and observation window.
- `unknown` indicates hidden query identity for at least one returned row.
- `temp_io_bytes` multiplies block operations by `block_size`; the same block can be read/written more than once, so it is not unique temp-file size.

## Common fault causes
- Sort/hash/materialize work exceeding available memory, large grouping/distinct operations, or an inefficient plan.
- Expected analytical processing.
- Long statistics windows or entry eviction/recreation.

## Checklist
- Divide temp blocks by calls and account for entry age before tuning.
- Inspect safe representative plans for sort method, disk usage, and hash batches.
- Tune query/indexes first; do not raise global `work_mem` without concurrency and memory analysis.
- Empty can mean no tracked statements or no rows after reset; unsupported means the extension view is unavailable.
