# CPU Utilization

This instruction belongs to report item `snapshot_charts_os.os_cpu_utilization`. The item is backed by `os.cpu_utilization` (snapshot metric).

## What this item shows
- CPU utilization over the snapshot window by mode.
- User, system, iowait, idle, and related CPU percentages where collected.

## What to watch
- Sustained high user or system CPU.
- iowait rising with disk latency.
- CPU saturation during SQL time spikes.

## Common fault causes
- CPU-bound queries.
- Parallel workers.
- Kernel overhead.
- Storage waits showing as iowait.

## Automatic evaluation
- The stacked modes use one CPU-tick denominator and should sum to approximately 100% after rounding.
- Guest time is excluded from the denominator because Linux already includes it in user/nice counters.

## Related report items
- [snapshot_charts_os.os_cpu_load](#item-snapshot_charts_os.os_cpu_load) — Compare CPU busy time with runnable and uninterruptible task pressure.
- [backend_os.backend_proc_cpu](#item-backend_os.backend_proc_cpu) — Identify PostgreSQL backends consuming CPU.
- [sql_workload.top_sql_by_total_time](#item-sql_workload.top_sql_by_total_time) — Check cumulative SQL associated with CPU pressure.

## Checklist
- Align peaks with Top SQL and backend_proc_cpu.
- Separate CPU saturation from I/O wait.
- Repeat capture during peak traffic.
