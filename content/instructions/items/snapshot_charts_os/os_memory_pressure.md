# Memory Pressure

This instruction belongs to report item `snapshot_charts_os.os_memory_pressure`. The item is backed by `os.memory_pressure` (snapshot metric).

## What this item shows
- Memory pressure signals collected during snapshots mode.
- Whether the host shows sustained shortage symptoms rather than normal cache use.

## What to watch
- Pressure spikes during workload peaks.
- Swap or reclaim indicators.
- Memory pressure coinciding with latency.

## Common fault causes
- RAM undersized.
- work_mem overuse.
- Non-database process pressure.
- Container limit too low.

## Checklist
- Confirm with OS tools if pressure is high.
- Reduce concurrency or memory-heavy operations before raising PostgreSQL memory settings.
- Check cgroup/container limits where applicable.
