# Database Transaction Rate

This instruction belongs to report item `snapshot_charts_db.database_transaction_rate`. The item is backed by `database.transaction_rate` (snapshot metric).

## What this item shows
- Commit and rollback rates over the snapshot window.
- Current transaction throughput for the connected database.

## What to watch
- Commit rate spikes.
- Rollback rate rising with errors.
- Throughput dropping during waits.

## Common fault causes
- Traffic burst.
- Application retry/errors.
- Lock waits or I/O bottleneck reducing throughput.

## Automatic evaluation
- Commit rate subtracts exactly one known pg_diag sample-transaction commit per interval; rollback rate is unadjusted.
- Counter decreases produce missing points rather than zero; no universal throughput severity is assigned.

## Checklist
- Compare with database_workload_delta.
- Check application error logs for rollback spikes.
- Align throughput changes with wait and SQL charts.
