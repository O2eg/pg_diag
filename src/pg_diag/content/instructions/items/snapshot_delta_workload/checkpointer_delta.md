# Checkpointer Delta

This instruction belongs to report item `snapshot_delta_workload.checkpointer_delta`.

## What this item shows
- Checkpoint and restartpoint counter deltas during the snapshot window. Exact completed checkpoints are available only on PostgreSQL 18 and newer; PostgreSQL 10-17 mark that field unsupported because their trigger counters also include idle skips.
- Buffers and SLRU buffers written plus checkpoint/restartpoint write and synchronization time. The write/sync counters include restartpoints on every supported PostgreSQL version.

## What to watch
- Repeated requested checkpoints, high buffer volume, or synchronization time aligned with latency spikes.
- PostgreSQL 10-16 expose the older checkpoint counters through `pg_stat_bgwriter`.
- Restartpoint event counters are null and marked unsupported before PostgreSQL 17. Exact completed checkpoints are unavailable before PostgreSQL 18, and `slru_written` is unavailable before PostgreSQL 18.
- Trigger counters can be published when an operation starts, completed counts and phase time when it finishes, and buffer progress while it runs. A checkpoint crossing a window endpoint can therefore move related deltas into different captures.

## Automatic evaluation
- No severity is assigned because a requested checkpoint is not independently proof of a fault.

## Interval coverage
- The row is valid only while the relevant shared statistics reset timestamp remains unchanged.

## Common fault causes
- WAL volume, manual CHECKPOINT, small `max_wal_size`, bulk writes, and slow checkpoint storage.

## Related report items
- [snapshot_delta_workload.wal_activity_delta](#item-snapshot_delta_workload.wal_activity_delta) — Relate checkpoint activity to WAL generation.
- [snapshot_delta_workload.background_writer_delta](#item-snapshot_delta_workload.background_writer_delta) — Separate checkpointer and background-writer work.
- [snapshot_charts_os.os_disk_latency](#item-snapshot_charts_os.os_disk_latency) — Check host write latency.

## Checklist
- Correlate with WAL Activity Delta, Background Writer Delta, PostgreSQL I/O Delta, and OS latency.
- On PostgreSQL 18 and newer, compare trigger and completed totals only across a window containing both the start and finish of the operation.
- Review checkpoint settings only after confirming the observed workload phase.
