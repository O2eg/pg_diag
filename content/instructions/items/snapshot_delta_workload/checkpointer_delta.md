# Checkpointer Delta

This instruction belongs to report item `snapshot_delta_workload.checkpointer_delta`.

## What this item shows
- Checkpoints and restartpoints requested, scheduled, and completed during the snapshot window.
- Buffers and SLRU buffers written plus checkpoint write and synchronization time.

## What to watch
- Repeated requested checkpoints, high buffer volume, or synchronization time aligned with latency spikes.
- PostgreSQL 14-16 expose the older checkpoint counters through `pg_stat_bgwriter`.
- Restartpoint counters are null and marked unsupported before PostgreSQL 17; `slru_written` is null and marked unsupported before PostgreSQL 18.

## Automatic evaluation
- No severity is assigned because a requested checkpoint is not independently proof of a fault.

## Interval coverage
- The row is valid only while the relevant shared statistics reset timestamp remains unchanged.

## Common fault causes
- WAL volume, manual CHECKPOINT, small `max_wal_size`, bulk writes, and slow checkpoint storage.

## Checklist
- Correlate with WAL Activity Delta, Background Writer Delta, PostgreSQL I/O Delta, and OS latency.
- Review checkpoint settings only after confirming the observed workload phase.
