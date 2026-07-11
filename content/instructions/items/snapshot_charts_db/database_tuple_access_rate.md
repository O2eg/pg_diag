# Database Tuple Access Rate

This instruction belongs to report item `snapshot_charts_db.database_tuple_access_rate`. The item is backed by `database.tuple_access_rate` (snapshot metric).

## What this item shows
- Separate tuple-returned and tuple-fetched rates at database level.
- Current row access volume over time.

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

## Checklist
- Compare with Top SQL and table scan deltas.
- Check whether high row access is expected.
- Review plans for fanout or missing predicates.
