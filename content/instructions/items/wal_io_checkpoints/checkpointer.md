# Checkpointer

This instruction belongs to report item `wal_io_checkpoints.checkpointer`. The item is backed by `checkpoints.checkpointer` (SQL query).

## What this item shows
- PostgreSQL 17+ cumulative checkpoint/restartpoint requests, completed restartpoints, write/sync time, buffers written, and reset age.
- PostgreSQL 18 adds completed checkpoint count, completion percentage, and SLRU buffers written.
- PostgreSQL 14-16 checkpoint counters are reported in the Background Writer item instead.

## What to watch
- Requested checkpoints increasing faster than timed checkpoints, high write/sync time deltas, or restartpoints repeatedly requested but not completed.
- PostgreSQL 18 completion percentage in context: idle servers can legitimately skip requested/timed checkpoints.

## Automatic evaluation
- No automatic severity: cumulative checkpoint counts require rate, reset age, workload, and storage context.
- Unsupported before PostgreSQL 17 by design; equivalent counters are shown by `pg_stat_bgwriter` there.

## Common fault causes
- Low `max_wal_size`, short checkpoint timeout, write bursts, slow fsyncs, or recovery restartpoint constraints.

## Checklist
- Calculate deltas and average write/sync time per completed event where the version exposes completion.
- Correlate with WAL generation, background writer, `pg_stat_io`, and OS latency.
- Do not treat every skipped checkpoint/restartpoint as a fault.
