# Background Writer

This instruction belongs to report item `wal_io_checkpoints.bgwriter`. The item is backed by `checkpoints.bgwriter` (SQL query).

## What this item shows
- Cluster-wide cumulative background-writer buffer cleaning, max-write stops, allocations, and reset age.
- PostgreSQL 10-16 also include checkpoint and backend-write/fsync counters; PostgreSQL 17 moved checkpoint data to `pg_stat_checkpointer`.

## What to watch
- `maxwritten_clean` increasing rapidly, client/backend writes dominating, or backend fsyncs on PostgreSQL 10-16.
- Allocation and cleaning rates rather than raw totals alone.

## Automatic evaluation
- PostgreSQL 10-16: `medium` when client backends have performed their own fsyncs since reset.
- PostgreSQL 17+: no equivalent backend-fsync counter remains in this view; inspect relation rows in `pg_stat_io`.
- Other cumulative volumes remain contextual.

## Common fault causes
- Dirty-buffer churn, conservative bgwriter limits, checkpoint pressure, slow storage, or bulk write workloads.

## Related report items
- [snapshot_delta_workload.background_writer_delta](#item-snapshot_delta_workload.background_writer_delta) — Measure background-writer work in the window.
- [wal_io_checkpoints.checkpointer](#item-wal_io_checkpoints.checkpointer) — Separate background-writer and checkpointer behavior.
- [wal_io_checkpoints.pg_stat_io](#item-wal_io_checkpoints.pg_stat_io) — Inspect relation I/O contexts.

## Checklist
- Calculate rates from two captures with the same reset epoch.
- Correlate with checkpointer, relation I/O contexts, and OS latency.
- Tune bgwriter/checkpoint settings only after confirming sustained behavior and storage headroom.
