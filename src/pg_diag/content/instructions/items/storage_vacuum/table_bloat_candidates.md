# Table Bloat Candidates

This instruction belongs to report item `storage_vacuum.table_bloat_candidates`. The item is backed by `storage.table_bloat_candidates` (SQL query).

## What this item shows
- A statistical bloat estimate for the 500 largest tables and materialized views (10 MB and up): expected heap size derived from `pg_stats` column widths, tuple headers, alignment, and fillfactor, compared with the actual `relpages`.
- The estimate reads only catalogs and planner statistics; table data is never scanned, so the item is safe on databases with hundreds of thousands of tables.
- `dead_rows` and `last_analyzed` provide live evidence next to the estimate; TOAST size is shown separately and its bloat is not estimated.
- `can_estimate` with `estimate_caveat` states when and why an estimate is refused instead of inventing numbers.

## What to watch
- Large `wasted_bytes` together with high `bloat_percent` on tables the workload reads heavily.
- A stale `last_analyzed`: the whole estimate is only as fresh as the statistics behind it.
- Rows with `can_estimate = false`: those tables are unassessed, not healthy.
- The estimate has a typical error of 10-30% and undercounts tables with dropped columns; treat every number as a candidate, not a verdict.

## Common fault causes
- Mass UPDATE or DELETE waves that autovacuum reclaimed for reuse but never returned to the filesystem.
- Autovacuum starved by long transactions, replication slots, or too-low cost limits.
- Low fillfactor combined with workloads that never benefit from HOT updates.

## Automatic evaluation
- `high` when estimated bloat is at least 60% and 5 GiB; `medium` at 40% and 1 GiB; both are statistical signals to verify, not rewrite orders.
- `unknown` when the estimate is refused (no statistics, missing column statistics, or restricted pg_stats access).
- Candidates are the 500 largest tables by `relpages`; truncation is marked. Tables never vacuumed or analyzed can carry a zero `relpages` and stay below the candidate threshold.

## Related report items
- [storage_vacuum.table_size_detailed](#item-storage_vacuum.table_size_detailed) — Exact size breakdown of the largest tables.
- [storage_vacuum.autovacuum_queue](#item-storage_vacuum.autovacuum_queue) — Whether autovacuum keeps up with dead tuples.
- [storage_vacuum.xmin_horizon](#item-storage_vacuum.xmin_horizon) — What blocks dead-tuple removal cluster-wide.
- [storage_vacuum.index_bloat_candidates](#item-storage_vacuum.index_bloat_candidates) — The index-side estimate for the same problem.

## Checklist
- Verify a high estimate with pgstattuple_approx during a quiet window before scheduling any rewrite.
- Fix the cause first: autovacuum starvation, xmin holders, or oversized delete batches.
- Choose the mitigation deliberately: plain VACUUM stops growth, pg_repack or VACUUM FULL returns space.
