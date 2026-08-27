# Standby Replay Delay

This instruction belongs to report item `snapshot_charts_db.standby_replay_delay`. The item is backed by `replication.standby_replay_delay` (metric over `metrics.standby_replay_delay`).

## What this item shows
- On a standby: the time since the last replayed transaction commit (`pg_last_xact_replay_timestamp`) at every sample, in seconds.
- This is the staleness a read replica exposes to its clients.

## What to watch
- A delay that grows linearly: no new transactions are replayed, either because the primary is idle or because replay is stalled.
- A delay that stays above `recovery_min_apply_delay` on delayed replicas.
- Delay peaks aligned with receive-to-replay lag peaks: replay is the bottleneck, not the primary's activity.

## Common fault causes
- An idle primary; the delay then reflects inactivity rather than a fault, so compare it with WAL rates.
- Paused or delayed replay.
- Replay slowed by conflicts or I/O.

## Automatic evaluation
- Charts are informational and assign no severity; an idle primary makes the delay grow without any fault.
- The chart stays empty on a primary.

## Related report items
- [snapshot_charts_db.standby_wal_rate](#item-snapshot_charts_db.standby_wal_rate) — Distinguish an idle primary from stalled replay.
- [snapshot_charts_db.standby_replay_lag_bytes](#item-snapshot_charts_db.standby_replay_lag_bytes) — Check whether unreplayed WAL is accumulating.
- [replication.standby_recovery_state](#item-replication.standby_recovery_state) — Verify the pause state and `recovery_min_apply_delay`.

## Checklist
- Confirm that the primary generated transactions during the window before treating the delay as lag.
- Compare the delay with the staleness the read workload tolerates.
