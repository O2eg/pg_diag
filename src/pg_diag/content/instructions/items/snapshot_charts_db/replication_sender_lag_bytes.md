# Replication Sender Lag Bytes

This instruction belongs to report item `snapshot_charts_db.replication_sender_lag_bytes`. The item is backed by `replication.sender_lag_bytes` (metric over `metrics.replication_sender_lag_bytes`).

## What this item shows
- For every WAL sender observed during the snapshot window: the byte distance between the local WAL position and the standby's sent, flushed, and replayed positions at every sample.
- One series group per sender (`application_name`, client address, and PID), so a reconnecting standby appears as a new group.

## What to watch
- Replay lag that grows steadily while sent lag stays flat: the standby cannot apply WAL as fast as it receives it (slow storage, recovery conflicts, or paused replay).
- Sent lag that grows: the network or the sender cannot keep up with WAL generation.
- Lag that never returns to zero after a burst.

## Common fault causes
- Bulk loads, index builds, or `VACUUM FULL` generating WAL faster than the standby applies it.
- Standby storage slower than the primary's.
- `recovery_min_apply_delay` or a paused replay on the standby.

## Automatic evaluation
- Charts are informational and assign no severity; lag thresholds depend on the workload and the recovery policy.
- Up to 50 senders are sampled per snapshot; a sender whose lag stayed at zero for the whole window is omitted from the chart, so an empty chart with connected standbys means they kept up at every sample.

## Related report items
- [replication.physical_replication](#item-replication.physical_replication) — Inspect the sender state at collection time.
- [snapshot_charts_db.replication_sender_lag_seconds](#item-snapshot_charts_db.replication_sender_lag_seconds) — Compare byte lag with time lag.
- [snapshot_charts_db.wal_growth_rate](#item-snapshot_charts_db.wal_growth_rate) — Correlate lag with WAL generation.

## Checklist
- Correlate lag peaks with WAL growth and workload items in the same window.
- Check the standby's storage and replay state when replay lag dominates.
