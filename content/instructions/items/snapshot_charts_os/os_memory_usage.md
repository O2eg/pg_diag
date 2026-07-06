# Memory Usage

This instruction belongs to report item `snapshot_charts_os.os_memory_usage`. The item is backed by `os.memory_usage` (snapshot metric).

## What this item shows
- RAM used, available, cache, and related memory gauges over time.
- Whether memory pressure changes during the capture.

## What to watch
- MemAvailable falling quickly.
- Swap-related pressure.
- Memory drop during query bursts.

## Common fault causes
- Too many backends.
- Large sorts/hashes.
- Colocated services.
- Kernel cache pressure.

## Checklist
- Compare with Memory Information.
- Check PostgreSQL memory settings and connection count.
- Inspect temp I/O when memory pressure aligns with spills.
