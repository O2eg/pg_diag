# Top Tables By Insert Rate

This instruction belongs to report item `snapshot_charts_db.tables_top_insert_rate`. The item is backed by `objects.tables_top_insert_rate` (snapshot metric).

## What this item shows
- Tables with highest insert rate.
- Current insert-heavy relations.

## What to watch
- Insert spike on one table.
- Unexpected ingest table activity.
- Insert rate aligned with WAL pressure.

## Common fault causes
- Bulk load.
- Queue/event table growth.
- Retry creating duplicates.
- New feature rollout.

## Checklist
- Check table growth and sequence capacity.
- Compare with WAL growth.
- Confirm retention/partitioning for insert-heavy tables.
