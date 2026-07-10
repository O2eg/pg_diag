# Transactions Over 1 Minute

This instruction belongs to report item `activity_locks.long_transactions`. The item is backed by `activity.long_transactions` (SQL query).

## What this item shows
- Up to 100 client sessions in the cluster with an open transaction older than one minute.
- Active, idle-in-transaction, and aborted-idle states with transaction, state, query, wait, XID, and xmin context.
- Ages in seconds; `xid_age` remains null when neither `backend_xid` nor `backend_xmin` is available.

## What to watch
- Idle transactions, high transaction age, or an old xmin horizon.
- Active transactions much longer than the expected batch or request duration.
- A session that also appears as a lock blocker.

## Automatic evaluation
- `high`: an idle transaction is at least one hour old, or an active transaction is at least one day old.
- `medium`: any idle transaction over one minute, or an active transaction at least 15 minutes old.
- Active transactions between one and 15 minutes are shown without severity because legitimate batch work is environment-specific.

## Common fault causes
- Missing commit or rollback, a paused client, or an abandoned interactive session.
- Batch/report queries with broad transaction scope.
- Application or job timeouts that do not cancel the database transaction.

## Checklist
- Confirm ownership, workload expectations, blocker impact, and xmin impact before cancellation.
- Prefer `pg_cancel_backend` for active work; terminate a session only when cancellation cannot resolve the open transaction and operational policy permits it.
- Correct transaction boundaries and configure appropriate statement and idle-transaction timeouts.
- An empty table means no matching transaction was observed; it does not describe transactions that ended before collection.
