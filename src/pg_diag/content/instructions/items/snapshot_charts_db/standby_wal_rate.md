# Standby WAL Receive And Replay Rate

This instruction belongs to report item `snapshot_charts_db.standby_wal_rate`. The item is backed by `replication.standby_wal_rate` (metric over `metrics.standby_wal_rate`).

## What this item shows
- On a standby: the rate at which WAL is received (`pg_last_wal_receive_lsn`) and replayed (`pg_last_wal_replay_lsn`) between snapshots, in bytes per second.
- On a primary the source returns no rows and the chart stays empty.

## What to watch
- Replay rate consistently below receive rate: replay falls behind and lag accumulates.
- Receive rate dropping to zero while the primary is busy: the streaming connection stalled.
- Replay rate of zero with a positive receive rate: replay is paused or blocked by a conflict.

## Common fault causes
- Standby storage slower than the primary's.
- Paused replay or `recovery_min_apply_delay`.
- Network throughput limits between primary and standby.

## Automatic evaluation
- Charts are informational and assign no severity.
- Rates come from LSN positions; a timeline switch during the window produces a gap rather than a negative rate.

## Related report items
- [snapshot_charts_db.standby_replay_lag_bytes](#item-snapshot_charts_db.standby_replay_lag_bytes) — See the accumulated receive-to-replay distance.
- [replication.standby_recovery_state](#item-replication.standby_recovery_state) — Check the replay pause state and delay settings.
- [replication.wal_receiver](#item-replication.wal_receiver) — Inspect the streaming connection.

## Checklist
- Compare replay rate with the primary's WAL generation rate.
- Check standby I/O charts when replay lags behind receive.
