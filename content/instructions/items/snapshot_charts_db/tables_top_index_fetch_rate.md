# Top Tables By Index Fetch Rate

This instruction belongs to report item `snapshot_charts_db.tables_top_index_fetch_rate`. The item is backed by `objects.tables_top_index_fetch_rate` (snapshot metric).

## What this item shows
- Tables with highest tuple fetch rate through indexes.
- Current index-driven table access hotspots.

## What to watch
- High fetch rate from one table.
- Fetch spike without matching transaction rate.
- Index access concentrated on hot relation.

## Common fault causes
- Hot lookup table.
- N+1 query pattern.
- Batch job using index lookups.

## Checklist
- Compare with Top SQL by Calls.
- Review whether caching/batching is possible.
- Check index_workload for the specific indexes.
