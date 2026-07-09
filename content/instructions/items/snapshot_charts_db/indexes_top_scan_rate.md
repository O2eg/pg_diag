# Top Indexes By Scan Rate

This instruction belongs to report item `snapshot_charts_db.indexes_top_scan_rate`. The item is backed by `objects.indexes_top_scan_rate` (snapshot metric).

## What this item shows
- Indexes with highest scan rate during the capture.
- Current index usage frequency.

## What to watch
- One index scanned far more than others.
- Unexpected index becoming hot after release.
- Scan rate without useful tuple fetches.

## Bounded samples
- Each SQL sample is ordered and limited before rows enter collector memory.
- Each column ranks deltas only for keys present in both adjacent bounded samples.
- Different index series between columns are expected; unmatched keys are not zero or errors.
- Counter decreases and invalid values are omitted and reported separately.

## Common fault causes
- Hot lookup path.
- N+1 query pattern.
- Plan change.
- Low-selectivity predicate.

## Checklist
- Map index to Top SQL plans.
- Check tuple read/fetch ratios.
- Avoid dropping indexes active in incident window.
