# Top Indexes By Scan Rate

This instruction belongs to report item `snapshot_charts_db.indexes_top_scan_rate`. The item is backed by `objects.indexes_top_scan_rate` (snapshot metric).

## What this item shows
- Indexes with highest scan rate during the capture.
- Current index usage frequency.

## What to watch
- One index scanned far more than others.
- Unexpected index becoming hot after release.
- Scan rate without useful tuple fetches.

## Common fault causes
- Hot lookup path.
- N+1 query pattern.
- Plan change.
- Low-selectivity predicate.

## Checklist
- Map index to Top SQL plans.
- Check tuple read/fetch ratios.
- Avoid dropping indexes active in incident window.
