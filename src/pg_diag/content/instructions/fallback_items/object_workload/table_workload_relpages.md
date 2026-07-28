# Approximate Table Workload Counters From relpages

This instruction belongs to report item `fallback.object_workload.table_workload_relpages`. The item is backed by `objects.table_workload_relpages` (SQL query).

## What this item shows
- The table workload counters that remain available after the primary table-workload query reaches `statement_timeout` or `lock_timeout`.
- An approximate main-relation size calculated as `pg_class.relpages × block_size`.
- For a partitioned table, the estimate sums the physical table descendants visible through `pg_inherits`.

Only the size estimate is aggregated through the partition tree. Workload,
tuple, vacuum, and analyze counters remain the counters reported by
`pg_stat_all_tables` for the displayed root relation; they are not summed from
its partitions.

## What to watch
- High sequential scans and tuple reads on tables with a large estimated main-relation size.
- High DML combined with growing dead-tuple estimates or stale vacuum and analyze timestamps.
- A zero or unexpectedly small estimate after recent bulk growth.
- A large partition-tree estimate beside zero root counters; inspect the leaf partitions before concluding that the tree is idle.

## Common fault causes
- The primary item waited while `pg_total_relation_size` inspected a relation that conflicted with concurrent DDL.
- The primary item exceeded its statement timeout while calculating exact sizes for the bounded candidate set.
- `relpages` is stale because VACUUM, ANALYZE, or size-changing DDL has not refreshed the catalog estimate.

## Automatic evaluation
- The sequential-scan finding uses the same cumulative scan thresholds as the primary item.
- `estimated_table_size_bytes` covers physical main relations in the table or partition tree. It does not include indexes, TOAST relations, free-space maps, visibility maps, or relation forks.
- The estimate is diagnostic prioritization data and must not be treated as an exact replacement for `pg_total_relation_size`.
- Partition-tree traversal is capped at 3,000 relation rows. `tree_truncated = true` means displayed page estimates are partial.

## Related report items
- [object_workload.table_workload](#item-object_workload.table_workload) — Retry the primary item when exact total relation sizes are required.
- [snapshot_delta_workload.table_scan_delta](#item-snapshot_delta_workload.table_scan_delta) — Compare cumulative counters with current scan rates.

## Checklist
- Confirm the fallback trigger in item metadata.
- Use the workload counters even when the estimated size is stale.
- If `tree_truncated = true`, do not use the partial size estimate to rank or compare complete partition trees.
- Run ANALYZE on a suitable maintenance path before relying on relpages for prioritization.
- Calculate exact sizes separately only when production locking and I/O conditions permit it.
