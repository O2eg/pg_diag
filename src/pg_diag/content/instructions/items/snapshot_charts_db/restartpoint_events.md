# Restartpoints By Trigger

This instruction belongs to report item `snapshot_charts_db.restartpoint_events`. The item is backed by `checkpoints.restartpoint_events` (snapshot metric).

## What this item shows
- Deltas of restartpoint counters published between consecutive snapshots: `timed` for timeout or a retry after a failed attempt, `requested` for restartpoints requested by recovery/checkpointer logic, and `done` for restartpoints that were performed.
- On a standby, requested restartpoints are commonly driven by replayed WAL reaching the distance governed by the standby's `max_wal_size`; they do not imply a manual or explicit user request.
- A primary creates no new restartpoint deltas. Cumulative counters from an earlier standby period can remain non-zero after promotion, but the chart becomes empty once consecutive samples are equal.
- Counters from `pg_stat_checkpointer`, so the item is unsupported before PostgreSQL 17.
- A trigger can become visible before its restartpoint finishes, while `done` becomes visible after completion. Long restartpoints can therefore place those increments in different interval columns; totals converge only for performed restartpoints fully contained by the capture window.

## What to watch
- Requested restartpoints rising while done stays flat across the full capture: inspect whether eligible checkpoint records from the primary arrived and whether an operation crossed the capture boundary.
- Few done restartpoints across a long capture while the primary produces checkpoints; standby recovery after a crash may then replay more WAL.
- Restartpoints coinciding with replay delay spikes.

## Common fault causes
- Primary checkpoints spaced far apart.
- A small `max_wal_size` on the standby.
- Slow replay or slow standby storage.

## Automatic evaluation
- No severity is assigned: a requested restartpoint that was not performed is expected until the next checkpoint record arrives.
- A statistics reset produces a missing interval rather than zero.
- A series that stays at zero for the whole window is omitted from the chart.

## Related report items
- [snapshot_delta_workload.checkpointer_delta](#item-snapshot_delta_workload.checkpointer_delta) — Window totals for restartpoint counters.
- [wal_io_checkpoints.checkpointer](#item-wal_io_checkpoints.checkpointer) — Cumulative restartpoint counters.
- [replication.standby_recovery_state](#item-replication.standby_recovery_state) — Confirm whether the server is currently in recovery.
- [snapshot_charts_db.standby_replay_delay](#item-snapshot_charts_db.standby_replay_delay) — Replay delay on the same standby.
- [snapshot_charts_db.standby_wal_rate](#item-snapshot_charts_db.standby_wal_rate) — WAL receive and replay throughput.

## Checklist
- Confirm the server is a standby before reading an empty chart as a problem; a short window can legitimately contain no restartpoint.
- Compare trigger and `done` totals over the full capture before investigating a single-column mismatch.
- Use PostgreSQL logs when exact restartpoint and primary-checkpoint spacing is required.
- Check replay delay when restartpoints coincide with lag.
