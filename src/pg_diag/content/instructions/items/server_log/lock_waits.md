# Lock Waits From Server Log

This instruction belongs to report item `server_log.lock_waits`. The item is backed by `server_log.lock_waits` (trusted Python source) and consumes the csvlog window collected with `--log-depth-time-min`.

## What this item shows
- Every lock wait that exceeded `deadlock_timeout` during the window, from `log_lock_waits` messages: who waited (`waiting_pid`), on what (`lock_type`, `target_kind`, clickable `relation_oid`/`database_oid`), and for how long (`wait_ms`). Up to the newest 200 matching log records are listed; summary counts and severity still use every matched record in the collected window.
- Two event kinds: `waiting` (the wait was still in progress when logged) and `acquired` (the wait resolved; `wait_ms` is the final duration). A `waiting` event with no matching `acquired` one was cancelled, timed out, or outlived the window.
- `holder_pids` and `queue_depth` come from the record's detail field: the sessions holding the lock and the total reported wait queue length, including `waiting_pid` itself.
- Unlike the live blocking lock tree, this is the history of the whole window, not the single moment of collection.

## What to watch
- `AccessExclusiveLock` waits on relations: DDL or maintenance blocking regular traffic — the summary raises these to `high` past 10 seconds.
- Large `queue_depth`: one holder serializing many sessions.
- Repeating waits on the same relation across the window: a chronic ordering problem, not an incident.

## Common fault causes
- Migrations or maintenance running without lock timeouts during business hours.
- Long transactions holding row locks while waiting on external systems.
- Batch jobs colliding with online traffic on the same hot rows.

## Automatic evaluation
- `high`: an `AccessExclusiveLock` wait above 10 s, or any wait above 60 s.
- `medium`: any recorded wait (each row already exceeded `deadlock_timeout`).
- `ok`: none; with `log_lock_waits = off` the item stays empty — enable it to collect this evidence.
- An empty result with an incomplete window is reported as unproven, not as absence.

## Related report items
- [activity_locks.blocking_lock_tree](#item-activity_locks.blocking_lock_tree) — The live lock tree at collection time.
- [activity_locks.lock_waits](#item-activity_locks.lock_waits) — Sessions waiting right now.
- [server_log.deadlock_events](#item-server_log.deadlock_events) — Conflicts that ended in a deadlock instead of a wait.

## Checklist
- Identify the holder from `holder_pids` and correlate with long transactions.
- Give DDL and maintenance a `lock_timeout` so they fail fast instead of queueing traffic.
- Fix recurring waiters by ordering lock acquisition consistently.
