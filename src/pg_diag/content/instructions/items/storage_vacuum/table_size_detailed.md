# Top Table Size Breakdown

This instruction belongs to report item `storage_vacuum.table_size_detailed`. The item is backed by `storage.table_size_detailed` (SQL query).

## What this item shows
- Exact heap/FSM/VM/index/TOAST sizes for the largest 100 rows among 200 candidates preselected by `pg_class.relpages` estimate.
- Stable table OID plus database/schema/table labels.

## What to watch
- Index or TOAST size dominating heap, and growth confirmed across separate reports.

## Automatic evaluation
- No automatic severity: size is capacity evidence, not proof of bloat or over-indexing.

## Common fault causes
- Legitimate data growth, wide values, many indexes, retention drift, or bloat.

## Related report items
- [overview.database_volume](#item-overview.database_volume) — Compare relation size with total database volume.
- [indexes.large_indexes](#item-indexes.large_indexes) — Identify index-heavy size amplification.
- [buffer_cache.top_relations](#item-buffer_cache.top_relations) — Check whether large relations dominate shared buffers.

## Checklist
- Candidate selection is deliberately bounded for databases with very many relations; stale `relpages` can omit a recently grown table.
- Relations holding a granted AccessExclusiveLock are skipped to avoid blocking diagnostics.
- Use bloat-specific evidence before rewrite/reindex decisions.
