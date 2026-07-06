# Top Table Size Breakdown

This instruction belongs to report item `storage_vacuum.table_size_detailed`. The item is backed by `storage.table_size_detailed` (SQL query).

## What this item shows
- Top relation size breakdown by heap, indexes, toast, and total bytes.
- Which tables consume the most storage.
- Storage distribution that hints at index or toast-heavy tables.

## What to watch
- Large table with index size much larger than heap.
- Toast size dominating total size.
- Rapidly growing relation after workload change.

## Common fault causes
- Bloat.
- Wide toasted columns.
- Over-indexing.
- Retention policy not running.
- Bulk load.

## Checklist
- Prioritize large active tables for deeper review.
- Compare with DML and vacuum evidence.
- Use bloat-specific tooling before scheduling rewrites.
