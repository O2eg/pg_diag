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

## Checklist
- Align peaks with Top SQL and backend_proc_cpu.
- Separate CPU saturation from I/O wait.
- Repeat capture during peak traffic.
