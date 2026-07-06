# Long Active Transactions

This instruction belongs to report item `activity_locks.long_transactions`. The item is backed by `activity.long_transactions` (SQL query).

## What this item shows
- Active and idle transactions ordered by transaction age.
- XID age and query text for sessions that can hold locks or xmin.
- Which user, application, and client owns long-running transactions.

## What to watch
- Transactions older than normal request duration.
- Long xact age combined with lock waits or xmin blockers.
- Long queries from unexpected application_name.

## Common fault causes
- Batch jobs without timeout.
- Report queries left running.
- Application transaction boundaries too broad.
- Client paused while transaction remains open.

## Checklist
- Check whether the transaction is blocking vacuum or other sessions.
- Contact owner before cancellation when possible.
- Set statement and idle transaction timeouts where appropriate.
