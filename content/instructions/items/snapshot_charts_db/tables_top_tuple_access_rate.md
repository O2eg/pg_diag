# Top Tables By Tuple Access Rate

This instruction belongs to report item `snapshot_charts_db.tables_top_tuple_access_rate`. The item is backed by `objects.tables_top_tuple_access_rate` (snapshot metric).

## What this item shows
- Tables with highest tuple access rate.
- Current table-level row access hotspots.

## What to watch
- One table dominating tuple reads/fetches.
- Unexpected table in top list.
- Access spike without matching business event.

## Common fault causes
- Report query.
- Join fanout.
- Missing predicate.
- Hot OLTP table.

## Checklist
- Inspect top table queries.
- Compare with table_scan_delta.
- Check indexes and statistics for hot tables.
