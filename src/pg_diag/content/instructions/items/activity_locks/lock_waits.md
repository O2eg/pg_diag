# Lock Waits

This instruction belongs to report item `activity_locks.lock_waits`. The item is backed by `locks.lock_waits` (SQL query).

## What this item shows
- Current blocked client sessions in the connected database and exact direct blockers returned by `pg_blocking_pids()`.
- Hard blockers and soft blockers ahead in a lock queue, including blocker PID zero for a prepared transaction.
- Waiting-lock target/mode, blocker transaction context, and whether the direct blocker is itself blocked.
- On PostgreSQL 14 and newer, `blocked_ms` is the exact age derived from `pg_locks.waitstart` and `blocked_duration_source = pg_locks.waitstart`.
- PostgreSQL 10–13 do not expose `pg_locks.waitstart`; there `blocked_ms` is derived from `pg_stat_activity.query_start`, `blocked_duration_source = pg_stat_activity.query_start_upper_bound`, and the value is only an upper bound for the lock-wait duration.
- Coverage fields showing whether blocked sessions, blocker pairs, direct blocker arrays, upstream blocker arrays, or the final 1,000-row result were truncated.
- `pg_locks` is read once for the bounded set of relevant backend PIDs; waiting and representative blocker locks are derived from that snapshot.

## What to watch
- Waits lasting more than normal statement latency.
- `blocker_is_root = false`, which means follow `blocker_blocked_by_pids` further up the chain.
- PID zero, which requires inspection of `pg_prepared_xacts` rather than backend cancellation.

## Automatic evaluation
- On PostgreSQL 14 and newer, `high` means an exact lock wait has lasted at least five minutes and `medium` means at least five seconds.
- Shorter PostgreSQL 14+ waits remain visible without severity. A briefly null `waitstart` produces unknown duration, not zero.
- PostgreSQL 10–13 rows remain `unknown` because query age can substantially exceed lock-wait age; do not apply the five-second/five-minute thresholds to the approximation.
- Collection evaluates at most 3,000 blocked sessions and 3,000 blocker pairs, at most 50 direct blockers per blocked PID, and at most 50 upstream blockers per pair.
- `blocked_sessions_truncated`, `blocking_pairs_truncated`, `direct_blockers_truncated`, `upstream_blockers_truncated`, and `result_truncated` explicitly identify incomplete output.

## Common fault causes
- Long or idle transactions holding row, transaction-ID, relation, object, or advisory locks.
- DDL during traffic, foreign-key contention, or hot-row updates.
- An abandoned prepared transaction.

## Related report items
- [activity_locks.long_transactions](#item-activity_locks.long_transactions) — Check whether the blocker is a long-running transaction.
- [activity_locks.wait_events](#item-activity_locks.wait_events) — Compare blocker detail with the current wait population.
- [sql_workload.top_sql_by_total_time](#item-sql_workload.top_sql_by_total_time) — Find cumulative SQL evidence for involved query IDs.

## Checklist
- Follow the blocker chain to a root session or prepared transaction before taking action.
- Confirm owner, transaction age, and business impact; query text can be the blocker's latest statement rather than the statement that acquired the lock.
- Prefer correcting transaction scope and scheduling over repeated manual termination.
- Empty means no current blocker pair was observed. Lock state can change while system views are read, so validate live before intervention.
