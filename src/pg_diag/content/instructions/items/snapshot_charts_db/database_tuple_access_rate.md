# Database Tuple Access Rate

This instruction belongs to report item `snapshot_charts_db.database_tuple_access_rate`. The item is backed by `database.tuple_access_rate` (snapshot metric).

## What this item shows
- Separate tuple-returned and tuple-fetched rates at database level.
- Current row access volume over time.

## Units
- `tuples/s` means PostgreSQL tuple-counter increments per wall-clock second. Tuples are logical row-processing events, not unique rows or physical storage blocks.

## What to watch
- Rows returned much higher than expected.
- Fetch/read spikes during report workload.
- Access rate changes without transaction-rate change.

## Common fault causes
- Large result sets.
- Sequential scans.
- Join fanout.
- Reporting query.

## Automatic evaluation
- The two counters are lines, not a stack: `tup_returned` and `tup_fetched` describe different executor/statistics stages and should not be added as total rows.
- Collector catalog queries contribute some `tup_returned` activity; use object and SQL deltas for attribution.

## Related report items
- [snapshot_delta_workload.table_scan_delta](#item-snapshot_delta_workload.table_scan_delta) — Attribute tuple access to table scans.
- [sql_workload.top_sql_by_total_time](#item-sql_workload.top_sql_by_total_time) — Find SQL associated with high tuple processing.
- [snapshot_charts_db.database_block_access_rate](#item-snapshot_charts_db.database_block_access_rate) — Compare logical tuples with block activity.

## Checklist
- Compare with Top SQL and table scan deltas.
- Check whether high row access is expected.
- Review plans for fanout or missing predicates.
