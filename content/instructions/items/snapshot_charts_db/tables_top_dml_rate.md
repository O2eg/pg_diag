# Top Tables By DML Rate

This instruction belongs to report item `snapshot_charts_db.tables_top_dml_rate`. The item is backed by `objects.tables_top_dml_rate` (snapshot metric).

## What this item shows
- Tables with highest combined insert/update/delete rate.
- Current write hotspots by table.

## What to watch
- One table dominating writes.
- DML spike during incident.
- Writes on unexpected relation.

## Common fault causes
- Batch load.
- Purge job.
- Application release change.
- Hot queue table.

## Checklist
- Compare with table_dml_delta and WAL growth.
- Check autovacuum pressure on top tables.
- Review application owner of write path.
