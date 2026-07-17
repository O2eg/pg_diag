# Database Transaction Rate

This instruction belongs to report item `snapshot_charts_db.database_transaction_rate`. The item is backed by `database.transaction_rate` (snapshot metric).

## What this item shows
- Commit and rollback rates over the snapshot window.
- Transaction throughput for every named database, partitioned by database.

## Units
- `transactions/s` (`tx/s` in the metric declaration) means committed or rolled-back transactions per wall-clock second, calculated from adjacent `pg_stat_database` counter samples.

## What to watch
- Commit rate spikes.
- Rollback rate rising with errors.
- Throughput dropping during waits.

## Common fault causes
- Traffic burst.
- Application retry/errors.
- Lock waits or I/O bottleneck reducing throughput.

## Automatic evaluation
- Commit and rollback rates are direct `pg_stat_database` counter deltas without collector-specific correction.
- Counter decreases produce missing points rather than zero; no universal throughput severity is assigned.

## Related report items
- [snapshot_delta_workload.database_workload_delta](#item-snapshot_delta_workload.database_workload_delta) — Inspect commit and rollback deltas with other database counters.
- [snapshot_charts_db.database_deadlocks](#item-snapshot_charts_db.database_deadlocks) — Check concurrency failures during transaction bursts.
- [activity_locks.connection_pressure](#item-activity_locks.connection_pressure) — Compare throughput with connection pressure.

## Checklist
- Compare with database_workload_delta.
- Check application error logs for rollback spikes.
- Align throughput changes with wait and SQL charts.
