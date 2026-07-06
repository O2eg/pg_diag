# Checkpointer

This instruction belongs to report item `wal_io_checkpoints.checkpointer`. The item is backed by `checkpoints.checkpointer` (SQL query).

## What this item shows
- Checkpoint and restartpoint counters on PostgreSQL versions with pg_stat_checkpointer.
- Buffers written, write time, sync time, and checkpoint frequency.
- Checkpoint contribution to write latency.

## What to watch
- Frequent requested checkpoints.
- High checkpoint write or sync time.
- Restartpoints during recovery that lag behind workload.

## Common fault causes
- max_wal_size too low.
- checkpoint_timeout too low for workload.
- Slow storage syncs.
- Large write bursts.

## Checklist
- Check whether checkpoints are timed or requested.
- Compare with disk latency and WAL growth.
- Tune checkpoint settings only after confirming storage headroom.
