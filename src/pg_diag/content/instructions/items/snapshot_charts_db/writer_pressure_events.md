# Writer Pressure Events

This instruction belongs to report item `snapshot_charts_db.writer_pressure_events`. The item is backed by `checkpoints.writer_pressure_events` (snapshot metric).

## What this item shows
- Two event counters per snapshot interval.
- `bgwriter stops`: the background writer ended a cleaning round early because it reached `bgwriter_lru_maxpages` (`maxwritten_clean`).
- `backend fsyncs`: PostgreSQL 10-16 use `buffers_backend_fsync`; PostgreSQL 17 and newer sum `pg_stat_io` relation fsyncs in the normal context for every backend type except the checkpointer. The definitions are close but not identical across the version boundary.

## What to watch
- Repeated or large backend-fsync deltas. They indicate that processes could not rely entirely on auxiliary writer/checkpointer work, but one isolated fsync is not proof of a capacity fault.
- Background-writer stops recurring in most intervals; the page limit is binding.
- Stops rising together with backend writes in Buffer Writes By Process.

## Common fault causes
- `bgwriter_lru_maxpages` too low for the dirty-page churn.
- Writer/checkpointer capacity insufficient for a large dirty set, or slow storage.
- Write bursts from bulk loads.

## Automatic evaluation
- No severity is assigned at chart level. On PostgreSQL 10-16 only, the Background Writer Delta table raises `medium` when its legacy backend-fsync counter increased; PostgreSQL 17 and newer require review of this chart or PostgreSQL I/O Delta.
- A reset of either the `bgwriter` or `io` statistics family produces a missing interval rather than a cross-epoch delta.
- A series that stays at zero for the whole window is omitted from the chart.

## Related report items
- [snapshot_delta_workload.background_writer_delta](#item-snapshot_delta_workload.background_writer_delta) — Legacy window totals and the PostgreSQL 10-16 automatic backend-fsync rule.
- [snapshot_charts_db.buffer_writes_by_process](#item-snapshot_charts_db.buffer_writes_by_process) — Who wrote the buffers in the same intervals.
- [snapshot_delta_workload.postgresql_io_delta](#item-snapshot_delta_workload.postgresql_io_delta) — Fsync detail per backend type on PostgreSQL 16 and newer.
- [wal_io_checkpoints.bgwriter](#item-wal_io_checkpoints.bgwriter) — Cumulative background-writer counters.

## Checklist
- Correlate recurring backend fsyncs with backend writes, checkpoint activity, and storage latency before attributing a cause.
- Raise `bgwriter_lru_maxpages` and `bgwriter_lru_multiplier` when stops recur under normal load.
- Compare with checkpoint sync time and OS disk latency.
