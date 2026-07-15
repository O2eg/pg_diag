# Lock Waits

This instruction belongs to report item `activity_locks.lock_waits`. The item is backed by `locks.lock_waits` (SQL query).

## What this item shows
- Current blocked client sessions in the connected database and exact direct blockers returned by `pg_blocking_pids()`.
- Hard blockers and soft blockers ahead in a lock queue, including blocker PID zero for a prepared transaction.
- Waiting-lock target/mode, exact `pg_locks.waitstart` age, blocker transaction context, and whether the direct blocker is itself blocked.

## What to watch
- Waits lasting more than normal statement latency.
- `blocker_is_root = false`, which means follow `blocker_blocked_by_pids` further up the chain.
- PID zero, which requires inspection of `pg_prepared_xacts` rather than backend cancellation.

## Automatic evaluation
- `high`: a lock wait has lasted at least five minutes.
- `medium`: a lock wait has lasted at least five seconds.
- Shorter waits remain visible without severity. A briefly null `waitstart` produces unknown duration, not zero.

## Common fault causes
- Long or idle transactions holding row, transaction-ID, relation, object, or advisory locks.
- DDL during traffic, foreign-key contention, or hot-row updates.
- An abandoned prepared transaction.

## Checklist
- Follow the blocker chain to a root session or prepared transaction before taking action.
- Confirm owner, transaction age, and business impact; query text can be the blocker's latest statement rather than the statement that acquired the lock.
- Prefer correcting transaction scope and scheduling over repeated manual termination.
- Empty means no current blocker pair was observed. Lock state can change while system views are read, so validate live before intervention.
