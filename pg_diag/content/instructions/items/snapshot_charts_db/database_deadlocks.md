# Database Deadlocks

This instruction belongs to report item `snapshot_charts_db.database_deadlocks`. The item is backed by `database.deadlocks` (snapshot metric).

## What this item shows
- Deadlock counter changes over time.
- Whether deadlocks occurred during the snapshot window.

## What to watch
- Any positive deadlock delta.
- Deadlocks recurring after deployment.
- Deadlocks aligned with write bursts.

## Common fault causes
- Inconsistent transaction lock order.
- Concurrent updates of same rows.
- FK checks or trigger behavior.

## Automatic evaluation
- Each nonzero column is a deadlock counter increase in the adjacent interval and warrants application/log review.
- Counter reset produces a missing interval rather than zero.

## Related report items
- [activity_locks.lock_waits](#item-activity_locks.lock_waits) — Inspect current blocker chains.
- [activity_locks.long_transactions](#item-activity_locks.long_transactions) — Check long transactions participating in lock cycles.
- [snapshot_delta_workload.table_dml_delta](#item-snapshot_delta_workload.table_dml_delta) — Look for write bursts around deadlocks.

## Checklist
- Review PostgreSQL logs for deadlock details.
- Fix transaction ordering in application code.
- Compare with lock waits and write-heavy SQL.
