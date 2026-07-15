# Top Tables By Tuple Access Rate

This instruction belongs to report item `snapshot_charts_db.tables_top_tuple_access_rate`. The item is backed by `objects.tables_top_tuple_access_rate` (snapshot metric).

## What this item shows
- Tables with highest tuple access rate.
- Current table-level row access hotspots.

## What to watch
- One table dominating tuple reads/fetches.
- Unexpected table in top list.
- Access spike without matching business event.

## Bounded samples
- Each SQL sample is ordered and limited before rows enter collector memory.
- Each column ranks deltas only for keys present in both adjacent bounded samples.
- Different table series between columns are expected; unmatched keys are not zero or errors.
- Counter decreases and invalid values are omitted and reported separately.

## Common fault causes
- Report query.
- Join fanout.
- Missing predicate.
- Hot OLTP table.

## Automatic evaluation
- This chart is informational and ranks interval deltas for stable relation OIDs present in both bounded samples.
- Sequential reads plus index fetches are logical tuple counters, not physical I/O.

## Checklist
- Inspect top table queries.
- Compare with table_scan_delta.
- Check indexes and statistics for hot tables.
