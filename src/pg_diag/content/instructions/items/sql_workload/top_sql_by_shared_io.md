# Top SQL By Shared Block I/O

This instruction belongs to report item `sql_workload.top_sql_by_shared_io`. The item is backed by `statements.top_by_io` (SQL query).

## What this item shows
- Up to 50 current-database entries ranked by cumulative shared blocks read plus blocks written by the statement backend.
- Shared hits/read/dirtied/written, calculated read-plus-written bytes, I/O timing, execution time, rows, identity, and SQL text.
- `stats_since` on PostgreSQL 17+; PG17 also renamed statement shared-block timing columns, which the selected variant handles.

## What to watch
- High shared reads per call and high read time when `track_io_timing` is enabled.
- Dirtied/written blocks from statements expected to be read-only.
- Cache-hit counts interpreted as logical buffer accesses, not physical disk reads.

## Automatic evaluation
- I/O totals do not assign severity because large scans and writes can be legitimate.
- `unknown` means some statement identity is hidden, not that its counters are invalid.
- `shared_io_bytes` is block reads plus backend writes multiplied by `block_size`; it is cumulative I/O volume, not unique data size or all later checkpoint writes.

## Common fault causes
- Large scans, ineffective indexes, cold cache, bulk DML, or expected reporting workloads.
- `track_io_timing = off`, which leaves timing at zero while block counters remain valid.
- Long statistics windows or entry churn distorting comparisons.

## Related report items
- [snapshot_delta_workload.sql_io_delta](#item-snapshot_delta_workload.sql_io_delta) — Measure statement I/O in the capture window.
- [snapshot_delta_workload.table_io_delta](#item-snapshot_delta_workload.table_io_delta) — Attribute shared I/O to relations.
- [snapshot_charts_os.os_disk_latency](#item-snapshot_charts_os.os_disk_latency) — Check whether PostgreSQL I/O coincides with storage latency.

## Checklist
- Normalize counters by calls and entry age before comparing query shapes.
- Review plans with `BUFFERS` and correlate with table and host I/O evidence.
- Do not infer physical storage latency from block counts alone.
- Empty/unsupported semantics follow the capability item; collection is one-shot and bounded to 50 rows.
