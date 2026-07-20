# Top Tables By Sequential Tuple Read Rate

This instruction belongs to report item `snapshot_charts_db.tables_top_seq_read_rate`. The item is backed by `objects.tables_top_seq_read_rate` (snapshot metric).

## What this item shows
- Tables with highest sequential tuple read rate.
- Current sequential scan pressure by table.

## Units
- `tuples/s` means `seq_tup_read` counter increments per wall-clock second for each table: logical tuples visited by sequential scans, not storage blocks read.

## What to watch
- Large table with high seq read rate.
- Seq read spike after release.
- Top table not expected to be scanned.

## Bounded samples
- Each SQL sample is ordered and limited before rows enter collector memory.
- Each column ranks deltas only for keys present in both adjacent bounded samples.
- Different table series between columns are expected; unmatched keys are not zero or errors.
- Counter decreases and invalid values are omitted and reported separately.

## Common fault causes
- Missing index.
- Planner chose seq scan due to estimates.
- Report or batch scan.

## Automatic evaluation
- This chart is informational and ranks `seq_tup_read` interval deltas by stable relation OID.
- A high rate is not proof of a missing index; validate scan count, workload intent, and plans.

## Related report items
- [snapshot_delta_workload.table_scan_delta](#item-snapshot_delta_workload.table_scan_delta) — Inspect sequential scan counts and tuples.
- [indexes.tables_without_pk_or_unique](#item-indexes.tables_without_pk_or_unique) — Review key-design gaps on scanned tables.
- [sql_workload.top_sql_by_total_time](#item-sql_workload.top_sql_by_total_time) — Find SQL responsible for broad scans.

## Checklist
- Check table size and row counts.
- Review plans for queries touching the table.
- Run ANALYZE if estimates are stale.
