# Standby Recovery State

This instruction belongs to report item `replication.standby_recovery_state`. The item is backed by `replication.standby_recovery_state` (SQL query).

## What this item shows
- Whether the server is in recovery, the replay pause state, received and replayed LSNs, receive-to-replay lag, the last replayed transaction time, the current timeline, and control-file recovery data.
- The WAL receiver status and slot, `primary_slot_name`, and the primary connection target parsed from `primary_conninfo` or the receiver connection string as host, port, user, `sslmode`, and `application_name`; passwords and the raw connection string are never shown.
- Standby-side settings: `recovery_min_apply_delay`, `recovery_target_timeline`, whether `restore_command` is configured, `hot_standby`, `hot_standby_feedback`, `max_standby_*_delay`, and WAL receiver timeouts.
- On a primary the row shows `server_role = primary` with the standby settings that would apply after a failover.

## What to watch
- `replay_paused = true`: the standby stops applying WAL and its lag grows without any replication error.
- Streaming without a slot; the primary keeps WAL only for `wal_keep_size`.
- `recovery_min_apply_delay` set on a standby that serves read traffic expecting fresh data.
- `hot_standby_feedback = off` on standbys that run long queries, or `on` where primary bloat is a concern.
- A `min_recovery_end_timeline` behind the current timeline after a failover or PITR.

## Common fault causes
- `pg_wal_replay_pause()` issued during maintenance and never resumed.
- Standbys cloned without `primary_slot_name`.
- Delayed replicas used as read replicas by mistake.
- `application_name` missing from `primary_conninfo`, which breaks synchronous replication matching.

## Automatic evaluation
- `high`: WAL replay is paused or a pause is requested.
- `medium`: the standby streams without a replication slot.
- `unknown`: `hot_standby_feedback` is off on a standby.
- `ok`: all other states, including primaries.
- On PostgreSQL 10 and 11 the recovery.conf parameters are not exposed as settings; those columns are unsupported and the WAL receiver connection string supplies the primary target.

## Related report items
- [replication.wal_receiver](#item-replication.wal_receiver) — Inspect the streaming connection in detail.
- [replication.standby_conflicts](#item-replication.standby_conflicts) — Correlate cancelled standby queries with feedback and delay settings.
- [wal_io_checkpoints.wal_position](#item-wal_io_checkpoints.wal_position) — Compare receive and replay LSNs with the WAL position summary.
- [replication.replication_slots](#item-replication.replication_slots) — Verify the slot the standby uses on the primary.

## Checklist
- Resume replay with `pg_wal_replay_resume()` when maintenance is over.
- Attach every standby to a slot or size `wal_keep_size` for the longest expected outage.
- Set `application_name` in `primary_conninfo` for synchronous candidates.
