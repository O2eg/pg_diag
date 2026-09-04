# Reported Checkpoint And Restartpoint Phase Time

This instruction belongs to report item `snapshot_charts_db.checkpoint_write_sync_time_delta`. The item is backed by `checkpoints.write_sync_time_delta` (snapshot metric).

## What this item shows
- Deltas, in milliseconds, added to the cumulative write-phase and sync-phase counters between consecutive snapshots.
- On every supported PostgreSQL version, these counters include both checkpoints and restartpoints. PostgreSQL 10-16 expose them through `pg_stat_bgwriter`; PostgreSQL 17 and newer expose the same combined work through `pg_stat_checkpointer`.
- Phase time is added when an operation completes. A column therefore means "this much phase time was published in this interval", not "this much work occurred during this interval". A 27-second write phase can appear as a 27,000 ms delta in the interval containing its completion.

## What to watch
- High sync time relative to write time across completed operations: storage flush latency may be important, but verify it against checkpoint logs and OS disk latency.
- Repeated large publication deltas together with frequent checkpoint/restartpoint log records.
- On every supported version, distinguish primary checkpoints from standby restartpoints before changing checkpoint settings.
- Use checkpoint logs for exact write, sync, total duration, and completion time; the chart is useful for finding capture windows that deserve that correlation.

## Common fault causes
- Slow or saturated storage during fsync.
- A large dirty set written by each checkpoint.
- Frequent requested checkpoints because `max_wal_size` is small.
- Write cache flushes on the storage layer.

## Automatic evaluation
- No severity is assigned: acceptable checkpoint time depends on storage and workload.
- A checkpointer/background-writer statistics reset produces a missing interval rather than zero.

## Related report items
- [snapshot_charts_db.checkpoint_trigger_events](#item-snapshot_charts_db.checkpoint_trigger_events) — Trigger and completion counters published in the capture.
- [snapshot_charts_db.restartpoint_events](#item-snapshot_charts_db.restartpoint_events) — Restartpoint counters on PostgreSQL 17 and newer.
- [snapshot_charts_os.os_disk_latency](#item-snapshot_charts_os.os_disk_latency) — Host write latency for correlation with reported sync time.
- [snapshot_delta_workload.checkpointer_delta](#item-snapshot_delta_workload.checkpointer_delta) — Window totals for write and sync time.
- [server_log.checkpoints](#item-server_log.checkpoints) — Per-checkpoint write, sync, and total seconds from the log.

## Checklist
- Correlate the published millisecond deltas with checkpoint log records and OS disk latency before changing settings.
- Confirm whether the server was primary or standby and whether the work was a checkpoint or restartpoint.
- Review storage write-cache behaviour when sync time consistently dominates completed operations.
