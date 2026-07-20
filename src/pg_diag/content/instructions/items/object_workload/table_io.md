# Table I/O Counters

This instruction belongs to report item `object_workload.table_io`. The item is backed by `objects.table_io` (SQL query).

## What this item shows
- Cumulative heap, index, toast, and toast-index block I/O by table.
- Which relations cause buffer hits and physical reads.
- Table-level cache behavior since stats reset.

## What to watch
- High heap_blks_read on large active table.
- High toast reads for wide-row tables.
- Low hit ratio where working set should be cached.

## Common fault causes
- Large scans.
- Cold cache.
- Working set larger than memory.
- TOAST-heavy access pattern.

## Automatic evaluation
- This item is informational because physical-read expectations depend on workload and cache warm-up.
- Counters are cumulative from `stats_reset`; use table I/O deltas for the collection-window rate.
- Only the top 200 tables by cumulative block reads are retained.

## Related report items
- [snapshot_delta_workload.table_io_delta](#item-snapshot_delta_workload.table_io_delta) — Measure table I/O in the capture window.
- [sql_workload.top_sql_by_shared_io](#item-sql_workload.top_sql_by_shared_io) — Find statements associated with shared-block work.
- [buffer_cache.top_relations](#item-buffer_cache.top_relations) — Check whether important relations dominate shared buffers.

## Checklist
- Compare with SQL shared I/O.
- Check whether reads are expected for reporting/batch jobs.
- Inspect query plans for hot tables.
