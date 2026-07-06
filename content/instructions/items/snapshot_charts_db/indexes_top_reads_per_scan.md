# Top Indexes By Reads Per Scan

This instruction belongs to report item `snapshot_charts_db.indexes_top_reads_per_scan`. The item is backed by `objects.indexes_top_reads_per_scan` (snapshot metric).

## What this item shows
- Indexes with highest block reads per index scan.
- Index scans that are physically expensive per execution.

## What to watch
- High reads per scan for frequently used index.
- Large index read amplification.
- Reads per scan increased after data growth.

## Common fault causes
- Index bloat.
- Poor clustering/locality.
- Cold cache.
- Broad range scans.

## Checklist
- Inspect index size and bloat indicators.
- Review query predicates and LIMIT/order usage.
- Compare with storage latency before rebuilding.
