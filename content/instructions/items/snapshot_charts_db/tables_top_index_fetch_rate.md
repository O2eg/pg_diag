# Top Tables By Index Fetch Rate

This instruction belongs to report item `snapshot_charts_db.tables_top_index_fetch_rate`. The item is backed by `objects.tables_top_index_fetch_rate` (snapshot metric).

## What this item shows
- Tables with highest tuple fetch rate through indexes.
- Current index-driven table access hotspots.

## What to watch
- High fetch rate from one table.
- Fetch spike without matching transaction rate.
- Index access concentrated on hot relation.

## Bounded samples
- Each SQL sample is ordered and limited before rows enter collector memory.
- Each column ranks deltas only for keys present in both adjacent bounded samples.
- Different table series between columns are expected; unmatched keys are not zero or errors.
- Counter decreases and invalid values are omitted and reported separately.

## Common fault causes
- Hot lookup table.
- N+1 query pattern.
- Batch job using index lookups.

## Automatic evaluation
- This chart is informational and ranks index-driven heap fetch deltas by stable relation OID.
- Counter resets, changing bounded membership, and absent endpoints become missing evidence.

## Checklist
- Compare with Top SQL by Calls.
- Review whether caching/batching is possible.
- Check index_workload for the specific indexes.
