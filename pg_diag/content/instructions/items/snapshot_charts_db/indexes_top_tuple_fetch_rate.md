# Top Indexes By Tuple Fetch Rate

This instruction belongs to report item `snapshot_charts_db.indexes_top_tuple_fetch_rate`. The item is backed by `objects.indexes_top_tuple_fetch_rate` (snapshot metric).

## What this item shows
- Indexes with highest heap tuple fetch rate.
- Index paths returning table rows during the capture.

## Units
- `tuples/s` means `idx_tup_fetch` counter increments per wall-clock second for each index: heap tuples fetched by simple index scans, not index entries examined.

## What to watch
- High fetch rate on hot table index.
- Fetch spike after application release.
- Fetches concentrated in one relation.

## Bounded samples
- Each SQL sample is ordered and limited before rows enter collector memory.
- Each column ranks deltas only for keys present in both adjacent bounded samples.
- Different index series between columns are expected; unmatched keys are not zero or errors.
- Counter decreases and invalid values are omitted and reported separately.

## Common fault causes
- Hot lookup workload.
- Batch process.
- N+1 pattern.

## Automatic evaluation
- `idx_tup_fetch` is the per-index heap fetch counter for simple index scans and excludes some bitmap behavior.
- The chart is informational and matches adjacent bounded samples by stable index OID.

## Checklist
- Compare with Top SQL by calls and table fetch charts.
- Check whether workload should be cached or batched.
- Review plans using the index.
