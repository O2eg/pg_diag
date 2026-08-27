# Standby Receive To Replay Lag

This instruction belongs to report item `snapshot_charts_db.standby_replay_lag_bytes`. The item is backed by `replication.standby_replay_lag_bytes` (metric over `metrics.standby_replay_lag_bytes`).

## What this item shows
- On a standby: the byte distance between the last received and the last replayed WAL position at every sample.
- This is the WAL already on the standby that has not been applied yet; it grows when replay is slower than receive and shrinks when replay catches up.

## What to watch
- A lag that grows during the whole window: replay cannot keep up.
- A lag that stays constant and large: replay is paused or delayed.
- Sudden drops to zero after peaks: replay catches up in bursts, typically after a conflict resolution.

## Common fault causes
- Slow standby storage or CPU saturation on the standby.
- Paused replay, `recovery_min_apply_delay`, or recovery conflicts waiting on `max_standby_streaming_delay`.
- Heavy WAL records such as index builds or bulk loads.

## Automatic evaluation
- Charts are informational and assign no severity.
- The chart stays empty on a primary, and also when the lag was zero at every sample.

## Related report items
- [snapshot_charts_db.standby_wal_rate](#item-snapshot_charts_db.standby_wal_rate) — Compare receive and replay throughput.
- [snapshot_charts_db.standby_replay_delay](#item-snapshot_charts_db.standby_replay_delay) — See the same lag expressed as time.
- [replication.standby_conflicts](#item-replication.standby_conflicts) — Check whether conflicts stall replay.

## Checklist
- Identify the WAL-heavy operations on the primary during the peaks.
- Check the standby for paused replay or conflict waits.
