# Memory Information

This instruction belongs to report item `os.memory_info`. The item is backed by `os.memory_info` (local host script).

## What this item shows
- Detailed `/proc/meminfo` counters including available memory, swap, buffers, cache, and huge pages.
- Current host memory pressure context at collection time.

## What to watch
- Low `MemAvailable`
- Swap in use on a latency-sensitive database host.
- HugePages allocation inconsistent with PostgreSQL configuration.
- High dirty/writeback memory during write stalls.

## Common fault causes
- Too many PostgreSQL backends for RAM.
- Large work_mem consumers or maintenance jobs.
- OS memory pressure from colocated services.
- Huge page reservation mismatch.

## Checklist
- Compare `MemAvailable` with PostgreSQL memory settings.
- Check swap activity before increasing memory settings.
- Verify huge page settings if PostgreSQL expects them.
