# Synchronous Replication Status

This instruction belongs to report item `replication.synchronous_replication_status`. The item is backed by `replication.synchronous_status` (SQL query).

## What this item shows
- `synchronous_standby_names` parsed into `sync_method` (`FIRST`, `ANY`, or `none`), `required_sync_count`, and one row per configured standby name in priority order (`*` matches every sender).
- For each name: connected senders that match it, how many of them are `sync` or `quorum`, the best `sync_state`, and the largest replay lag.
- Cluster totals: connected senders, `sync`, `quorum`, and `potential` counts, `quorum_satisfied`, `synchronous_commit`, `commit_waits_for_standby`, and sessions waiting in `SyncRep`.
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
- `high`: the quorum is not satisfied and `synchronous_commit` waits for standbys.
- `medium`: the quorum is not satisfied but commits do not wait, or a configured standby has no connected sender while other candidates keep the quorum.
- `unknown`: names are configured but `synchronous_commit` is `off` or `local` at the server level, or the name or sender sample was truncated (100 names, 1,000 senders).
- `ok`: quorum satisfied, or asynchronous replication.
- `SyncRep` waiters are counted from `pg_stat_activity`; sessions of other roles are visible only with `pg_read_all_stats`.

## Related report items
- [replication.physical_replication](#item-replication.physical_replication) — Inspect each sender's LSNs, lag, and `sync_state`.
- [activity_locks.wait_events](#item-activity_locks.wait_events) — Confirm sessions waiting on `SyncRep`.
- [replication.replication_capacity](#item-replication.replication_capacity) — Check whether standbys cannot connect because `max_wal_senders` is exhausted.

## Checklist
- Match `application_name` values on standbys with `synchronous_standby_names`.
- Keep at least one more candidate than `required_sync_count` for `FIRST` and `ANY` quorums.
- Document the intended `synchronous_commit` level per role and database.
