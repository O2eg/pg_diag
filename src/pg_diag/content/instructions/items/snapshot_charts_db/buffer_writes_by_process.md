# Buffer Writes By Process

This instruction belongs to report item `snapshot_charts_db.buffer_writes_by_process`. The item is backed by `checkpoints.buffer_writes_by_process` (snapshot metric).

## What this item shows
- Deltas of cumulative buffer-write activity divided by wall-clock time between snapshots, stacked by the process that did the work: the checkpointer, the background writer, and other processes such as client backends, autovacuum, and parallel workers.
- Checkpointer and background-writer bytes are buffer counts multiplied by the server `block_size`. Their checkpointer series includes buffers written for both checkpoints and restartpoints on every supported PostgreSQL version.
- On PostgreSQL 10-16, the backend series is the legacy `buffers_backend` counter multiplied by `block_size`. It includes backend write/fsync registrations and relation-extension requests; multi-block extensions can be represented by one request, so this is an estimate rather than an exact byte count.
- On PostgreSQL 17, the backend series sums `writes + extends` from `pg_stat_io` and multiplies by `op_bytes`. On PostgreSQL 18 and newer, it sums `write_bytes + extend_bytes`. This definition deliberately includes relation extensions, but values around a 16-to-17 upgrade are not directly comparable with the legacy estimate.
- Checkpoint buffer progress is published incrementally while a paced checkpoint writes and sleeps. Such work can span several sampled intervals; a narrow spike is more typical of an immediate checkpoint, a checkpoint behind schedule, or sampling that is too coarse.

## What to watch
- Backends carrying a large share of writes: the background writer is not keeping clean buffers ahead of demand, or the working set does not fit `shared_buffers`.
- Sustained backend writes across several snapshots. Large values during bulk loads and maintenance are expected and must be separated from normal OLTP windows.
- Large checkpointer rates together with checkpoint/restartpoint log records. A paced checkpoint should normally occupy multiple intervals when the collection interval is short enough.
- The background writer near zero while backends write steadily.
- Bulk loads and `VACUUM` use ring buffers and write through backends by design; judge those windows separately.

## Common fault causes
- `shared_buffers` too small for the working set.
- `bgwriter_lru_maxpages` or `bgwriter_lru_multiplier` too low for the dirty-page churn.
- Checkpoints with a large dirty-buffer set or an aggressively low `checkpoint_completion_target`.
- Slow storage that lets dirty pages accumulate between checkpoints.

## Automatic evaluation
- No severity is assigned: the split between writers depends on workload and settings.
- A reset of any underlying `bgwriter`, `checkpointer`, or `io` statistics family produces a missing interval rather than a cross-epoch rate.

## Related report items
- [snapshot_delta_workload.background_writer_delta](#item-snapshot_delta_workload.background_writer_delta) — Window totals for the background-writer counters.
- [snapshot_delta_workload.postgresql_io_delta](#item-snapshot_delta_workload.postgresql_io_delta) — Per backend type and context detail from `pg_stat_io`.
- [snapshot_charts_db.io_read_write_rate](#item-snapshot_charts_db.io_read_write_rate) — Total PostgreSQL read and write throughput by backend type.
- [snapshot_charts_db.buffer_allocation_rate](#item-snapshot_charts_db.buffer_allocation_rate) — Shared-buffer allocation turnover in the same intervals.
- [snapshot_charts_db.writer_pressure_events](#item-snapshot_charts_db.writer_pressure_events) — Background-writer stops and backend fsyncs in the same window.

## Checklist
- Check whether backend writes coincide with bulk jobs before tuning the background writer.
- Compare checkpointer deltas with Checkpoint Triggers And Completions, restartpoint activity, and checkpoint log records.
- Do not compare the backend series across PostgreSQL 16 and 17 as if its accounting definition were unchanged.
- Review `shared_buffers` against the working set when allocation and backend writes are both high.
