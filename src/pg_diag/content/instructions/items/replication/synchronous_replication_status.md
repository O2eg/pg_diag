# Synchronous Replication Status

This instruction belongs to report item `replication.synchronous_replication_status`. The item is backed by `replication.synchronous_status` (SQL query).

## What this item shows
- `synchronous_standby_names` parsed into `sync_method` (`FIRST`, `ANY`, or `none`), `required_sync_count`, and one row per configured standby name in priority order (`*` matches every sender).
- For each name: connected senders that match it, how many of them are `sync` or `quorum`, the best `sync_state`, and the largest replay lag.
- Cluster totals: connected senders, `sync`, `quorum`, and `potential` counts, `quorum_satisfied`, sessions waiting in `SyncRep`, and `in_recovery`.
- `synchronous_commit` is the collector session's value; `synchronous_commit_override_count` and `synchronous_commit_overrides` list `ALTER ROLE` and `ALTER DATABASE` overrides, because the effective level differs per session and may be changed per transaction.
- With an empty `synchronous_standby_names`, one `[none]` row documents asynchronous replication.

## What to watch
- `quorum_satisfied = false` while `commit_waits_for_standby = true`: every commit waits until the missing standby reconnects.
- Growing `syncrep_waiting_sessions`.
- A configured name with `best_sync_state = absent`; the standby was renamed, stopped, or connects with a different `application_name`.
- `synchronous_commit = off` or `local` at the server level with names configured; synchronous durability then depends on per-role or per-transaction settings.

## Common fault causes
- Standby `application_name` in `primary_conninfo` differs from `synchronous_standby_names`.
- A synchronous standby was decommissioned without updating the primary.
- `FIRST n` with fewer than `n` reachable standbys after a failure.

## Automatic evaluation
- `high`: the quorum is not satisfied and sessions are waiting in `SyncRep`, or the quorum is not satisfied while `synchronous_commit` waits for standbys and no per-role or per-database override exists.
- `medium`: the quorum is not satisfied but overrides make the effective level session-dependent, the quorum is not satisfied while the collector session does not wait, or a configured standby has no connected sender while other candidates keep the quorum.
- `unknown`: the quorum is satisfied but overrides exist, or names are configured while the collector session uses `off` or `local`.
- `ok`: quorum satisfied, asynchronous replication, or a server in recovery (the setting applies only after promotion).
- A `[coverage]` row is added when names (100), senders (1,000), or overrides (100) were truncated; proven findings keep their severity.
- `SyncRep` waiters are counted from `pg_stat_activity`; sessions of other roles are visible only with `pg_read_all_stats`.

## Related report items
- [replication.physical_replication](#item-replication.physical_replication) — Inspect each sender's LSNs, lag, and `sync_state`.
- [activity_locks.wait_events](#item-activity_locks.wait_events) — Confirm sessions waiting on `SyncRep`.
- [replication.replication_capacity](#item-replication.replication_capacity) — Check whether standbys cannot connect because `max_wal_senders` is exhausted.

## Checklist
- Match `application_name` values on standbys with `synchronous_standby_names`.
- Keep at least one more candidate than `required_sync_count` for `FIRST` and `ANY` quorums.
- Document the intended `synchronous_commit` level per role and database.
