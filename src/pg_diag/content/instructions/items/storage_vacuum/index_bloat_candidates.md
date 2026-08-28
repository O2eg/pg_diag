# Index Bloat Candidates

This instruction belongs to report item `storage_vacuum.index_bloat_candidates`. The item is backed by `storage.index_bloat_candidates` (SQL query).

## What this item shows
- A statistical bloat estimate for the 500 largest indexes (10 MB and up): expected btree leaf size derived from indexed-column widths, tuple headers, alignment, and index fillfactor, compared with the actual `relpages`.
- Only catalogs and planner statistics are read; index pages are never scanned, so the item is safe with millions of indexes.
- Expression-index statistics are taken from the statistics PostgreSQL keeps for the index itself; `index_scans` shows whether the index is used at all.
- Non-btree indexes (GIN, GiST, hash, BRIN) are listed for size awareness with `can_estimate = false` - unassessed, not healthy.

## What to watch
- Large `wasted_bytes` on hot indexes: bloated btrees inflate every lookup and cache footprint.
- Bloated indexes with near-zero `index_scans`: dropping may beat rebuilding.
- On PostgreSQL 13 and newer, btree deduplication can make the actual index smaller than the estimate; negative differences are clamped to zero.
- The leaf-only model ignores internal pages (about 1% of a healthy btree), and the typical estimation error is 10-30%.

## Common fault causes
- Random-key churn (UUIDs, queue tables) that leaves half-empty leaf pages.
- Mass deletes whose index entries were reclaimed but pages never merged.
- Repeated updates of indexed columns defeating HOT.

## Automatic evaluation
- `high` when estimated bloat is at least 60% and 5 GiB; `medium` at 40% and 1 GiB; both are statistical signals to verify, not rebuild orders.
- `unknown` when estimation is refused (non-btree access method, missing statistics, or restricted pg_stats access).
- Candidates are the 500 largest indexes by `relpages`; truncation is marked.

## Related report items
- [storage_vacuum.table_bloat_candidates](#item-storage_vacuum.table_bloat_candidates) — The table-side estimate for the same problem.
- [indexes.unused_indexes](#item-indexes.unused_indexes) — Indexes that may deserve dropping instead of rebuilding.
- [indexes.large_indexes](#item-indexes.large_indexes) — Indexes disproportionately large against their table.

## Checklist
- Verify a high estimate before scheduling REINDEX CONCURRENTLY, and rebuild during a low-traffic window.
- For unused bloated indexes, confirm they back no constraint and consider dropping them.
- Recheck after the rebuild: quickly returning bloat points at a workload or fillfactor cause.
