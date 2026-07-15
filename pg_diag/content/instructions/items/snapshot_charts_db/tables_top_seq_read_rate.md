# Top Tables By Sequential Tuple Read Rate

This instruction belongs to report item `snapshot_charts_db.tables_top_seq_read_rate`. The item is backed by `objects.tables_top_seq_read_rate` (snapshot metric).

## What this item shows
- Tables with highest sequential tuple read rate.
- Current sequential scan pressure by table.

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

## Checklist
- Check table size and row counts.
- Review plans for queries touching the table.
- Run ANALYZE if estimates are stale.
