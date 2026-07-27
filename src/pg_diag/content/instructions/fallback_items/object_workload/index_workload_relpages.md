# Approximate Index Workload Counters From relpages

This instruction belongs to report item `fallback.object_workload.index_workload_relpages`. The item is backed by `objects.index_workload_relpages` (SQL query).

## What this item shows
- Index usage and cache-I/O counters collected after the primary index-workload query reaches `statement_timeout` or `lock_timeout`.
- An approximate index size calculated as `pg_class.relpages × block_size`.
- For a partitioned index represented in `pg_inherits`, the estimate sums its physical index descendants.

Only the size estimate is aggregated through the partition tree. Scan, tuple,
and block-I/O counters remain the statistics of the displayed index relation;
they are not summed from child indexes.

## What to watch
- Large estimated indexes with low scan activity.
- High block reads relative to hits on frequently used indexes.
- Zero or unexpectedly small estimates after index creation, rebuild, or rapid data growth.
- A large partition-tree estimate with low root activity; inspect the leaf-index counters before classifying the index as unused.

## Common fault causes
- The primary item waited while `pg_relation_size` inspected an index that conflicted with concurrent DDL.
- Exact size calculations for the candidate indexes exceeded the primary statement timeout.
- Catalog `relpages` values are stale until PostgreSQL refreshes them through maintenance or relevant DDL.

## Automatic evaluation
- This fallback does not infer that a low-use index is safe to remove.
- `estimated_index_size_bytes` estimates physical index pages and is not an exact relation-file measurement.
- Partition-tree estimates depend on complete and visible `pg_inherits` catalog data.

## Related report items
- [object_workload.index_workload](#item-object_workload.index_workload) — Retry the primary item when exact index sizes are required.
- [indexes.unused_indexes](#item-indexes.unused_indexes) — Review longer-term unused-index evidence before considering removal.

## Checklist
- Confirm the fallback trigger in item metadata.
- Compare `idx_scan`, tuple, and block counters with the statistics reset time.
- Validate relpages freshness before ranking indexes by estimated size.
- Use exact size functions later, outside a lock-sensitive collection window, if exact storage is required.
