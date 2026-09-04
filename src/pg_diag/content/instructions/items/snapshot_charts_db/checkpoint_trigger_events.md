# Checkpoint Triggers And Completions

This instruction belongs to report item `snapshot_charts_db.checkpoint_trigger_events`. The item is backed by `checkpoints.trigger_events` (snapshot metric).

## What this item shows
- Deltas of cluster-wide checkpoint counters published between consecutive snapshots, split into `timed`, `requested`, and, on PostgreSQL 18 and newer, `completed`.
- On every supported PostgreSQL version, `timed` and `requested` count checkpoint attempts by trigger class. They are incremented before the decision to skip an idle checkpoint, so neither series is a completed-checkpoint count.
- PostgreSQL 10-17 do not expose an exact completed-checkpoint counter. PostgreSQL 18 and newer expose `num_done` as `completed`; it increments only after a checkpoint is performed.
- Requested activity can come from WAL volume reaching `max_wal_size`, manual `CHECKPOINT`, backup activity, shutdown, and other explicit checkpoint requests; the counter does not identify the cause.
- Cluster-wide counters from `pg_stat_bgwriter` on PostgreSQL 10-16 and from `pg_stat_checkpointer` on PostgreSQL 17 and newer.
- Trigger counters can become visible while the checkpoint is still running, whereas `completed` becomes visible after it finishes. A long checkpoint can therefore put its trigger and completion into different interval columns; totals converge only for performed checkpoints whose trigger and completion both fall inside the capture window.

## What to watch
- Repeated requested increments across the capture, especially when checkpoint logs identify `wal` as the cause and WAL Growth Rate is sustained.
- On PostgreSQL 18 and newer, compare trigger and completion totals over the full capture. A per-interval difference can be normal publication skew; a whole-window excess can also come from idle skips or an operation crossing a capture boundary.
- A growing requested share across comparable captures. Treat it as a signal to inspect exact log reasons, not proof that `max_wal_size` is too small.
- Use checkpoint log timestamps for exact spacing and duration; snapshot columns are publication buckets rather than a checkpoint event timeline.

## Common fault causes
- `max_wal_size` too small for the write burst.
- Bulk loads, index builds, or large `VACUUM` runs.
- Manual `CHECKPOINT` from backup or deployment scripts.
- A short `checkpoint_timeout`.

## Automatic evaluation
- No severity is assigned: a requested checkpoint is not proof of a fault, and the healthy share depends on the workload.
- A checkpointer/background-writer statistics reset produces a missing interval rather than zero.
- A series that stays at zero for the whole window is omitted from the chart.

## Related report items
- [snapshot_delta_workload.checkpointer_delta](#item-snapshot_delta_workload.checkpointer_delta) — Totals for the same counters over the whole capture window.
- [snapshot_charts_db.wal_growth_rate](#item-snapshot_charts_db.wal_growth_rate) — Match requested checkpoints with WAL volume.
- [snapshot_charts_db.checkpoint_write_sync_time_delta](#item-snapshot_charts_db.checkpoint_write_sync_time_delta) — See write and sync time published by completed checkpoints and restartpoints.
- [server_log.checkpoints](#item-server_log.checkpoints) — Per-checkpoint log lines with the exact reason and buffers written.
- [wal_io_checkpoints.checkpointer](#item-wal_io_checkpoints.checkpointer) — Cumulative counters since the last statistics reset.

## Checklist
- Compare requested increments with WAL Growth Rate and checkpoint log reasons.
- Raise `max_wal_size` only when requested checkpoints coincide with sustained WAL volume, not one-off bulk jobs.
- On PostgreSQL 18 and newer, compare trigger and completion sums over the capture before investigating a single-column mismatch.
- Use checkpoint logs, not the distance between snapshot columns, to validate checkpoint spacing and duration.
