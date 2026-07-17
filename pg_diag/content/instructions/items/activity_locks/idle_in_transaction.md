# Idle In Transaction Over 1 Minute

This instruction belongs to report item `activity_locks.idle_in_transaction`. The item is backed by `activity.idle_in_transaction` (SQL query).

## What this item shows
- Up to 100 client sessions idle in an open transaction for more than one minute, including aborted transactions.
- Idle and transaction ages, user/application/client ownership, waits, XID/xmin context, and the last query.
- `xid_age` as null when no XID or xmin evidence is available rather than treating unavailable data as zero.

## What to watch
- Any persistent row on latency-sensitive OLTP systems.
- High transaction or XID age, especially with lock waits or vacuum lag.
- Repeated ownership by one pool or application path.

## Automatic evaluation
- `high`: idle in transaction for at least one hour.
- `medium`: idle in transaction for more than one minute.
- This is an instantaneous observation; a session that ended before collection is not represented.

## Common fault causes
- Application omitted commit or rollback.
- A client paused or disconnected while its server session remained alive.
- Pooler/session reuse with an open transaction.

## Related report items
- [activity_locks.long_transactions](#item-activity_locks.long_transactions) — Measure the transaction age retained by the idle session.
- [storage_vacuum.xmin_horizon_blockers](#item-storage_vacuum.xmin_horizon_blockers) — Check vacuum-horizon impact.
- [storage_vacuum.autovacuum_queue](#item-storage_vacuum.autovacuum_queue) — Look for maintenance pressure caused by retained tuples.

## Checklist
- Confirm the owner and transaction impact before terminating a backend.
- Fix application cleanup and rollback paths.
- Consider `idle_in_transaction_session_timeout` with an application-compatible value.
- Empty means no matching session at collection time; error or partial visibility is not a clean result.
