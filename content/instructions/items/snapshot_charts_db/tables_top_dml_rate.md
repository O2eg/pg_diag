# Top Tables By DML Rate

This instruction belongs to report item `snapshot_charts_db.tables_top_dml_rate`. The item is backed by `objects.tables_top_dml_rate` (snapshot metric).

## What this item shows
- Tables with highest combined insert/update/delete rate.
- Current write hotspots by table.

## What to watch
- One table dominating writes.
- DML spike during incident.
- Writes on unexpected relation.

## Bounded samples
- Each SQL sample is ordered and limited before rows enter collector memory.
- Each column ranks deltas only for keys present in both adjacent bounded samples.
- Different table series between columns are expected; unmatched keys are not zero or errors.
- Counter decreases and invalid values are omitted and reported separately.

## Common fault causes
- Batch load.
- Purge job.
- Application release change.
- Hot queue table.

## Automatic evaluation
- Insert/update/delete interval deltas share rows/second and are stacked per stable relation OID.
- Changing bounded membership and counter decreases become missing evidence, not zero.

## Checklist
- Compare with table_dml_delta and WAL growth.
- Check autovacuum pressure on top tables.
- Review application owner of write path.
