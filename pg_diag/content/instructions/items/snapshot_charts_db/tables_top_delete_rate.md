# Top Tables By Delete Rate

This instruction belongs to report item `snapshot_charts_db.tables_top_delete_rate`. The item is backed by `objects.tables_top_delete_rate` (snapshot metric).

## What this item shows
- Tables with highest delete rate.
- Current delete-heavy relations.

## What to watch
- Delete spike on large table.
- Deletes causing autovacuum lag.
- Unexpected purge activity.

## Bounded samples
- Each SQL sample is ordered and limited before rows enter collector memory.
- Each column ranks deltas only for keys present in both adjacent bounded samples.
- Different table series between columns are expected; unmatched keys are not zero or errors.
- Counter decreases and invalid values are omitted and reported separately.

## Common fault causes
- Retention job.
- Cascade delete.
- Application cleanup burst.
- Manual maintenance.

## Automatic evaluation
- This chart ranks delete counter deltas for stable relation OIDs present in both adjacent bounded samples.
- Delete rate becomes actionable only with retention, dead-tuple, WAL, or vacuum context.

## Checklist
- Check FK support indexes for cascades.
- Compare with dead tuples/autovacuum queue.
- Consider batching deletes.
