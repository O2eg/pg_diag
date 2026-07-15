# Top Tables By Update Rate

This instruction belongs to report item `snapshot_charts_db.tables_top_update_rate`. The item is backed by `objects.tables_top_update_rate` (snapshot metric).

## What this item shows
- Tables with highest update rate.
- Current update-heavy relations.

## What to watch
- High update rate on table with many indexes.
- Low HOT update behavior elsewhere in report.
- Unexpected updates after release.

## Bounded samples
- Each SQL sample is ordered and limited before rows enter collector memory.
- Each column ranks deltas only for keys present in both adjacent bounded samples.
- Different table series between columns are expected; unmatched keys are not zero or errors.
- Counter decreases and invalid values are omitted and reported separately.

## Common fault causes
- Hot-row updates.
- Frequent status changes.
- Index set prevents HOT updates.
- Batch correction job.

## Automatic evaluation
- This chart ranks update counter deltas for stable relation OIDs present in both adjacent bounded samples.
- Compare with HOT updates, dead tuples, and autovacuum evidence; rate alone is not a problem.

## Checklist
- Compare with WAL and autovacuum pressure.
- Review indexed columns being updated.
- Consider fillfactor/index design for hot tables.
