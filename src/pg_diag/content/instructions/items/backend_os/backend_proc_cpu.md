# PostgreSQL Backend /proc CPU

This instruction belongs to report item `backend_os.backend_proc_cpu`. The item is backed by `backend.proc_cpu_top` (window-endpoint metric).

## What this item shows
- Average CPU use per local PostgreSQL process over the snapshots window.
- The rate is calculated from two `/proc/<pid>/stat` counter reads: one at window start and one at window end.
- Only a process with the same PID and process start time at both endpoints can be included.

## What to watch
- One PID using most CPU over the full window.
- Parallel workers consuming CPU as a group.
- An empty result when PostgreSQL processes started or exited inside the window, or `/proc` is unavailable.

## Common fault causes
- CPU-bound query.
- Parallel plan.
- Autovacuum or maintenance job.
- Collector permission limits.

## Automatic evaluation
- This item is informational; expected CPU depends on core count, parallelism, and workload.
- PID reuse is rejected by matching the Linux process start time at both endpoints.
- A single process can exceed 100% on reporting conventions only if the underlying counter represents more than one execution context; PostgreSQL server processes normally represent one process.

## Related report items
- [backend_os.backend_activity](#item-backend_os.backend_activity) — Map sampled PIDs to database, user, state, and query.
- [sql_workload.top_sql_by_total_time](#item-sql_workload.top_sql_by_total_time) — Compare backend CPU with cumulative expensive SQL.
- [snapshot_charts_os.os_cpu_utilization](#item-snapshot_charts_os.os_cpu_utilization) — Place per-backend CPU in host-wide context.

## Checklist
- Use the PID and command to correlate with Backend Activity; this item does not contain a query ID.
- Group leader and parallel worker PIDs together.
- Treat the value as a window average, not a peak measurement.
- Run pg_diag locally with permissions required for `/proc` access.
