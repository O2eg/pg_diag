# PostgreSQL Backend /proc CPU

This instruction belongs to report item `backend_os.backend_proc_cpu`. The item is backed by `backend.proc_cpu_top` (window-endpoint metric).

## What this item shows
- Average CPU use per local PostgreSQL process over the snapshots window.
- The rate is calculated from two `/proc/<pid>/stat` counter reads: one at window start and one at window end.
- Only a process with the same PID and process start time at both endpoints can be included.
- Detailed collection is bounded to 2,000 PostgreSQL processes. If the host has
  more, running or uninterruptible processes are selected first and the
  remaining capacity follows the `ps` CPU ordering at discovery time.

## What to watch
- One PID using most CPU over the full window.
- Parallel workers consuming CPU as a group.
- An empty result when PostgreSQL processes started or exited inside the window, or `/proc` is unavailable.
- A `backend_process_limit` warning: the ranking covers only the reported
  bounded process set and can omit a backend which became busy later.
- A `backend_process_capture_incomplete` warning: some selected PIDs exited
  during capture or `/proc/<pid>/stat` was not readable. The warning reports
  selected and captured counts for both endpoints.

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
- Check the sampled/discovered process counts before treating the table as a
  complete host-wide Top CPU ranking.
- For incomplete capture, verify `/proc` mount options such as `hidepid`, the
  collector OS user, and PostgreSQL process churn during the endpoint reads.
- Run `pg-diag` locally with permissions required for `/proc` access.
