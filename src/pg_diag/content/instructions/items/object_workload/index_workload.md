# Index Workload Counters

This instruction belongs to report item `object_workload.index_workload`. The item is backed by `objects.index_workload` (SQL query).

## What this item shows
- Cumulative index scans, tuple reads/fetches, and index cache I/O.
- Which indexes are actively used and how much work they perform.
- Index-level read amplification context.

## What to watch
- High idx_tup_read with low idx_tup_fetch.
- High index block reads.
- Indexes with scan count inconsistent with expectations.

## Common fault causes
- Low-selectivity index.
- Bitmap scan workload.
- Bloated or oversized index.
- Plan change.

## Automatic evaluation
- This item is informational; scan counts cannot prove that an index is useful or safe to remove.
- Counters are cumulative from `stats_reset`, and the bounded result contains the top 100 indexes by scan count.
- Exact index size is calculated only after the candidate limit.
- `stats_window_start` and `stats_window_source` give a lower bound of the counter window: the counters have accumulated at least since that moment. It is the latest of the postmaster start, `pg_stat_database.stats_reset` (exact when set; on PostgreSQL 15+ it stays NULL until `pg_stat_reset()` is called) and the shared statistics reset time (`pg_stat_bgwriter.stats_reset`). A shared reset after the postmaster started is either a crash recovery, which discards every counter, or a targeted `pg_stat_reset_shared()`, which leaves per-object counters older, so the later time never overstates the window; statistics also survive clean restarts, so the true window may be longer than shown. An object created after `stats_window_start` has accumulated only since its creation, which the catalog does not record.

## Related report items
- [snapshot_delta_workload.index_usage_delta](#item-snapshot_delta_workload.index_usage_delta) — Measure index use during the capture window.
- [indexes.unused_indexes](#item-indexes.unused_indexes) — Review indexes with no recorded scans.
- [indexes.redundant_indexes](#item-indexes.redundant_indexes) — Check overlapping index definitions.

## Checklist
- Use with index health findings.
- Review plans for indexes with high reads per useful fetch.
- Do not drop indexes that are active in current workload.
