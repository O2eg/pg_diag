# Blocking Lock Tree

This instruction belongs to report item `activity_locks.blocking_lock_tree`. The item is backed by `locks.blocking_lock_tree` (SQL query).

## What this item shows
- Every blocking chain in the connected database as a tree walked from its root: the session that blocks others while not being blocked itself.
- `depth`, `path`, and `blocked_by_pid` describe each node's position; `root_blocked_sessions` counts how many sessions the root holds directly or transitively, and the trees are ordered largest first.
- `wait_event` shows what each session is doing right now; a root sitting in `Client: ClientRead` is an idle-in-transaction session waiting for its application.
- A session blocked by several sessions appears once under each of its blockers, so a chain can be listed under more than one root.

## What to watch
- The root of the largest tree: resolving it releases every session below it.
- Roots with a long `transaction_ms` and a `Client:` wait event; the blocking transaction is waiting for its client, not for the database.
- Deep chains (`depth` of two or more): intermediate sessions both wait and block, and cancelling them only moves the problem.
- Prepared transactions never appear as roots here because they have no backend PID; check the prepared transactions item when a visible root cannot explain a wait.

## Common fault causes
- An application transaction left open across user think-time or an external call.
- DDL or maintenance taking a strong table lock behind ordinary workload.
- Batch jobs updating the same rows as interactive traffic.

## Automatic evaluation
- A root that directly or transitively blocks 10 or more sessions reports `high`.
- Sessions behind a cascade at least two levels deep report `medium`.
- The tree is built from the first 1500 waiting sessions, follows at most 50 blockers per session and 5000 nodes, and guards against cycles; proven findings keep their severity even when a bound is exceeded, and the incomplete coverage is reported as a separate `[coverage]` row with `unknown`.
- `query_ms` is an upper bound for the lock wait; the exact wait duration is in the lock waits item on PostgreSQL 14 and newer.

## Related report items
- [activity_locks.lock_waits](#item-activity_locks.lock_waits) — Per-wait detail with lock modes, targets, and exact wait durations.
- [activity_locks.long_transactions](#item-activity_locks.long_transactions) — Long transactions that are the usual root blockers.
- [activity_locks.idle_in_transaction](#item-activity_locks.idle_in_transaction) — Idle-in-transaction sessions holding locks while waiting for their client.
- [storage_vacuum.prepared_xacts](#item-storage_vacuum.prepared_xacts) — Prepared transactions that hold locks without a backend PID.

## Checklist
- Start from the root of the largest tree and validate transaction ownership before cancelling or terminating it.
- Prefer pg_cancel_backend over pg_terminate_backend when the root is running a query.
- If waits persist with no visible root, check prepared transactions and locks taken in other databases.
