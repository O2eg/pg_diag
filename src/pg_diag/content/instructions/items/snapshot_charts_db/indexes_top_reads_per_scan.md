# Top Indexes By Tuples Read Per Scan

This instruction belongs to report item `snapshot_charts_db.indexes_top_reads_per_scan`. The item is backed by `objects.indexes_top_reads_per_scan` (snapshot metric).

## What this item shows
- The interval delta of index entries returned (`idx_tup_read`) divided by the interval delta of index scans.
- Logical index selectivity/work-per-scan evidence, not block reads or physical I/O.

## What to watch
- Many index entries returned per scan on a latency-sensitive lookup path.
- A ratio rising after data distribution or predicate changes.

## Bounded samples
- Each SQL sample is ordered and limited before rows enter collector memory.
- Ratios use only matching index OIDs present in both adjacent bounded samples.
- Changing Top-N membership is expected; unmatched keys and counter decreases become missing evidence, not zero.

## Common fault causes
- Broad range scans, low selectivity, bitmap scans, or an intentionally large result set.

## Automatic evaluation
- This chart is informational; the ratio does not measure cache misses, bloat, or physical read amplification.
- Very small scan deltas can create unstable ratios, so confirm scan volume and representative plans.

## Related report items
- [snapshot_charts_db.indexes_top_scan_rate](#item-snapshot_charts_db.indexes_top_scan_rate) — Check whether the ratio is supported by meaningful scan volume.
- [snapshot_charts_db.indexes_top_tuple_read_rate](#item-snapshot_charts_db.indexes_top_tuple_read_rate) — Inspect the numerator rate.
- [sql_workload.top_sql_by_total_time](#item-sql_workload.top_sql_by_total_time) — Review statements using inefficient access paths.

## Checklist
- Review predicates, index column order, scan count, and expected result cardinality.
- Use block-read and latency items for physical I/O conclusions.
