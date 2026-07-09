# Top Indexes By Reads Per Scan

This instruction belongs to report item `snapshot_charts_db.indexes_top_reads_per_scan`. The item is backed by `objects.indexes_top_reads_per_scan` (snapshot metric).

## What this item shows
- Indexes with highest block reads per index scan.
- Index scans that are physically expensive per execution.

## What to watch
- High reads per scan for frequently used index.
- Large index read amplification.
- Reads per scan increased after data growth.

## Bounded samples
- Each SQL sample is ordered and limited before rows enter collector memory.
- Each column ranks deltas only for keys present in both adjacent bounded samples.
- Different index series between columns are expected; unmatched keys are not zero or errors.
- Counter decreases and invalid values are omitted and reported separately.

## Common fault causes
- Index bloat.
- Poor clustering/locality.
- Cold cache.
- Broad range scans.

## Checklist
- Inspect index size and bloat indicators.
- Review query predicates and LIMIT/order usage.
- Compare with storage latency before rebuilding.
