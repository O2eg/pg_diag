# Memory Information

This instruction belongs to report item `os.memory_info`. The item is backed by `os.memory_info` (local host script).

## What this item shows
- Selected `/proc/meminfo` counters including available memory, swap, buffers, cache, dirty/writeback state, commit accounting, and huge pages.
- Kernel `kB` values are normalized to exact bytes; unitless HugePages counters remain counts.
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

## Automatic evaluation
- No severity is assigned from this point-in-time snapshot. Low available memory and nonzero swap require rate/PSI evidence and workload context.
- Missing kernel-version-specific fields are normal; `unsupported` means `/proc/meminfo` itself was unavailable.

## Checklist
- Compare `MemAvailable` with PostgreSQL memory settings.
- Check swap activity before increasing memory settings.
- Verify huge page settings if PostgreSQL expects them.
