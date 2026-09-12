# Indexes Large Relative To Table

This instruction belongs to report item `indexes.large_indexes`. The item is backed by `indexes.large_indexes` (SQL query).

## What this item shows
- Indexes larger than half of their table heap with usage counters, limited to tables whose heap is at least 1 MiB.
- Large index storage and maintenance-cost candidates.
- Index/table size imbalance.

## What to watch
- Large index with low scan count.
- Many large indexes on hot write table.
- Index size driven by wide columns or expressions.

## Common fault causes
- Bloat.
- Wide covering index.
- Low-selectivity multi-column index.
- Retention growth.

## Automatic evaluation
- This ratio is informational: a legitimate narrow table can have an index larger than its heap.
- Tables below 1 MiB are excluded; catalog page estimates pre-filter and select at most 100 candidates before exact size functions verify the threshold.
- Usage counters are cumulative from the reported `stats_reset`; size ratio alone is not bloat evidence.
- `stats_window_start` and `stats_window_source` give a lower bound of the counter window: the counters have accumulated at least since that moment. It is the latest of the postmaster start, `pg_stat_database.stats_reset` (exact when set; on PostgreSQL 15+ it stays NULL until `pg_stat_reset()` is called) and the shared statistics reset time (`pg_stat_bgwriter.stats_reset`). A shared reset after the postmaster started is either a crash recovery, which discards every counter, or a targeted `pg_stat_reset_shared()`, which leaves per-object counters older, so the later time never overstates the window; statistics also survive clean restarts, so the true window may be longer than shown. An object created after `stats_window_start` has accumulated only since its creation, which the catalog does not record.

## Related report items
- [storage_vacuum.table_size_detailed](#item-storage_vacuum.table_size_detailed) — Compare index and table size components.
- [object_workload.index_workload](#item-object_workload.index_workload) — Check whether large indexes are actively used.
- [snapshot_charts_db.tables_top_index_block_read_rate](#item-snapshot_charts_db.tables_top_index_block_read_rate) — Inspect physical index-read pressure.

## Checklist
- Check usage before dropping or rebuilding.
- Consider REINDEX only when bloat is confirmed.
- Review index design against actual query predicates.
