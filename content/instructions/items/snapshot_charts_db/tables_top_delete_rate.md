# Top Tables By Delete Rate

This instruction belongs to report item `snapshot_charts_db.tables_top_delete_rate`. The item is backed by `objects.tables_top_delete_rate` (snapshot metric).

## What this item shows
- Tables with highest delete rate.
- Current delete-heavy relations.

## What to watch
- Delete spike on large table.
- Deletes causing autovacuum lag.
- Unexpected purge activity.

## Common fault causes
- Retention job.
- Cascade delete.
- Application cleanup burst.
- Manual maintenance.

## Checklist
- Check FK support indexes for cascades.
- Compare with dead tuples/autovacuum queue.
- Consider batching deletes.
