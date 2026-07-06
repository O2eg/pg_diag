# CPU Information

This instruction belongs to report item `os.cpu_info`. The item is backed by `os.cpu_info` (local host script).

## What this item shows
- CPU topology, sockets, cores, threads, model, flags, and virtualization details from `lscpu`
- Hardware context for parallel query, background workers, and CPU saturation analysis.

## What to watch
- Fewer CPUs than expected.
- Disabled SMT or missing CPU flags required by extensions.
- Virtualization or NUMA layout different from the intended platform.

## Common fault causes
- Wrong VM size.
- BIOS or hypervisor CPU policy change.
- Container CPU quota hiding actual host capacity.

## Checklist
- Compare CPU count with PostgreSQL worker settings.
- Check NUMA and virtualization notes before tuning CPU-bound workload.
- Use CPU charts to confirm whether capacity is actually saturated.
