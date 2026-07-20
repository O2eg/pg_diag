# Top Indexes By Heap Fetches Per Scan

This instruction belongs to report item `snapshot_charts_db.indexes_top_fetches_per_scan`. The item is backed by `objects.indexes_top_fetches_per_scan` (snapshot metric).

## What this item shows
- Per-index heap tuple fetch delta divided by index scan delta for adjacent samples.
- Heap rows fetched by simple index scans; bitmap and index-only behavior affects interpretation.

## What to watch
- Many heap fetches per scan on a path expected to return a single row.
- Ratio changes after data distribution or plan changes.

## Bounded samples
- Samples are sorted/limited before memory and matched by stable index OID.
- Changing Top-N membership, counter reset, and absent endpoints produce missing evidence rather than zero.

## Common fault causes
- Low-selectivity predicates, broad range scans, or intentionally large indexed result sets.

## Automatic evaluation
- This is informational; a high ratio can be correct and a low ratio can reflect index-only or bitmap behavior.

## Related report items
- [snapshot_charts_db.indexes_top_scan_rate](#item-snapshot_charts_db.indexes_top_scan_rate) — Check scan volume behind the ratio.
- [snapshot_charts_db.indexes_top_tuple_fetch_rate](#item-snapshot_charts_db.indexes_top_tuple_fetch_rate) — Inspect the heap-fetch numerator.
- [sql_workload.top_sql_by_calls](#item-sql_workload.top_sql_by_calls) — Review repeated indexed lookups.

## Checklist
- Confirm scan volume, expected result cardinality, and representative plans before changing an index.
