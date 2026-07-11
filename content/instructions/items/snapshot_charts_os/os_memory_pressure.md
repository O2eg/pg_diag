# RAM And Swap Usage

This instruction belongs to report item `snapshot_charts_os.os_memory_pressure`. The item is backed by `os.memory_pressure` (snapshot metric).

## What this item shows
- Two independent line series: RAM used as `MemTotal - MemAvailable`, and swap used as `SwapTotal - SwapFree`.
- Each percentage has its own denominator, so the values are not stacked or added.
- This is usage evidence, not Linux PSI memory-pressure or paging-rate data.

## What to watch
- RAM usage rising while available memory approaches zero.
- Sustained or increasing swap use aligned with database latency.
- A sharp change during high connection or sort/hash concurrency.

## Common fault causes
- RAM or cgroup limit too small for the combined workload.
- Concurrent memory-heavy operations or too many backends.
- Pressure from colocated non-PostgreSQL processes.

## Automatic evaluation
- The chart is informational because a healthy Linux host normally uses most RAM for reclaimable cache.
- Swap usage alone does not prove active swapping; confirm with paging counters or OS tools.

## Checklist
- Compare with the memory composition chart, temp I/O, connection count, and workload timing.
- Check cgroup/container limits where applicable.
- Confirm paging activity before changing PostgreSQL memory settings.
