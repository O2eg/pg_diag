# Top Tables By Update Rate

This instruction belongs to report item `snapshot_charts_db.tables_top_update_rate`. The item is backed by `objects.tables_top_update_rate` (snapshot metric).

## What this item shows
- Tables with highest update rate.
- Current update-heavy relations.

## What to watch
- High update rate on table with many indexes.
- Low HOT update behavior elsewhere in report.
- Unexpected updates after release.

## Common fault causes
- Hot-row updates.
- Frequent status changes.
- Index set prevents HOT updates.
- Batch correction job.

## Checklist
- Compare with WAL and autovacuum pressure.
- Review indexed columns being updated.
- Consider fillfactor/index design for hot tables.
