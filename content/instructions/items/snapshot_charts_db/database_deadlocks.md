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

## Checklist
- Review PostgreSQL logs for deadlock details.
- Fix transaction ordering in application code.
- Compare with lock waits and write-heavy SQL.
