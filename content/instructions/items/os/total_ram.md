# Total RAM Capacity

This instruction belongs to report item `os.total_ram`. The item is backed by `os.total_ram` (local host script).

## What this item shows
- Host total RAM capacity from `/proc/meminfo`, stored as exact bytes and displayed with an adaptive IEC unit.
- Sizing evidence for shared_buffers, work_mem, maintenance_work_mem, and connection limits.

## What to watch
- RAM smaller than expected for the instance class or hardware.
- Capacity mismatch across cluster nodes.
- Configured memory budgets that exceed physical RAM.

## Common fault causes
- Wrong VM flavor or container limit.
- Hardware replacement or BIOS memory issue.
- Configuration copied from a larger host.

## Automatic evaluation
- No severity is assigned because adequate capacity depends on workload and PostgreSQL configuration.
- `/proc/meminfo` may describe the host rather than a container cgroup limit; validate container quotas separately.

## Checklist
- Confirm instance size or physical RAM inventory.
- Recalculate worst-case memory with max_connections and work_mem.
- Compare with `Memory Information` for current availability.
