# Top Indexes By Fetches Per Scan

This instruction belongs to report item `snapshot_charts_db.indexes_top_fetches_per_scan`. The item is backed by `objects.indexes_top_fetches_per_scan` (snapshot metric).

## What this item shows
- Indexes returning many heap tuples per scan.
- Indexes used for broad result sets rather than selective lookups.

## What to watch
- High fetches per scan on OLTP lookup path.
- Unexpected broad index scans.
- Fetches per scan rising after data distribution change.

## Common fault causes
- Low-selectivity predicate.
- Missing additional filter column in index.
- Report query using broad range.

## Checklist
- Check query predicates and selectivity.
- Consider composite or partial indexes only with plan evidence.
- Validate whether broad result set is expected.
