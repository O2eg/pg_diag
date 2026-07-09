# Top Indexes By Reads Per Fetch

This instruction belongs to report item `snapshot_charts_db.indexes_top_reads_per_fetch`. The item is backed by `objects.indexes_top_reads_per_fetch` (snapshot metric).

## What this item shows
- Indexes with high block reads relative to fetched tuples.
- Potentially inefficient physical access per useful row.

## What to watch
- High reads per fetched tuple.
- Index read cost high while returned rows are low.
- Storage reads concentrated in one index.

## Bounded samples
- Each SQL sample is ordered and limited before rows enter collector memory.
- Each column ranks deltas only for keys present in both adjacent bounded samples.
- Different index series between columns are expected; unmatched keys are not zero or errors.
- Counter decreases and invalid values are omitted and reported separately.

## Common fault causes
- Index bloat.
- Poor cache locality.
- Low-selectivity or stale stats.
- Cold cache.

## Checklist
- Review plans and index size.
- Run ANALYZE if estimates are stale.
- Consider REINDEX only with bloat evidence.
