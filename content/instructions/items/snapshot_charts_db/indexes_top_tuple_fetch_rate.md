# Top Indexes By Tuple Fetch Rate

This instruction belongs to report item `snapshot_charts_db.indexes_top_tuple_fetch_rate`. The item is backed by `objects.indexes_top_tuple_fetch_rate` (snapshot metric).

## What this item shows
- Indexes with highest heap tuple fetch rate.
- Index paths returning table rows during the capture.

## What to watch
- High fetch rate on hot table index.
- Fetch spike after application release.
- Fetches concentrated in one relation.

## Common fault causes
- Hot lookup workload.
- Batch process.
- N+1 pattern.

## Checklist
- Compare with Top SQL by calls and table fetch charts.
- Check whether workload should be cached or batched.
- Review plans using the index.
