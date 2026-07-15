# Memory Usage

This instruction belongs to report item `snapshot_charts_os.os_memory_usage`. The item is backed by `os.memory_usage` (snapshot metric).

## What this item shows
- A stacked accounting view of free RAM, page cache, shared memory, buffers, slab, selected kernel allocations, and a residual application bucket.
- Whether memory pressure changes during the capture.

## What to watch
- Free memory and reclaimable components changing quickly; use the separate RAM/swap chart for `MemAvailable`-based usage.
- Swap-related pressure.
- Memory drop during query bursts.

## Common fault causes
- Too many backends.
- Large sorts/hashes.
- Colocated services.
- Kernel cache pressure.

## Automatic evaluation
- This chart is informational; the residual application bucket is not per-process attribution.
- The stack is constructed to remain bounded by `MemTotal`; it is not a Linux PSI signal.

## Checklist
- Compare with Memory Information.
- Check PostgreSQL memory settings and connection count.
- Inspect temp I/O when memory pressure aligns with spills.
