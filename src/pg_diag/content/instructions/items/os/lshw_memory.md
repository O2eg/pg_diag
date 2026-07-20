# System Memory Hardware

This instruction belongs to report item `os.lshw_memory`. The item is backed by `os.lshw_memory` (local host script).

## What this item shows
- Physical memory modules and memory hardware metadata when visible.
- Memory size, banks, and hardware characteristics from lshw.

## What to watch
- Missing modules, degraded memory, or unexpected capacity.
- Inventory unavailable because of permissions.

## Common fault causes
- Hardware failure or replacement.
- BIOS configuration change.
- lshw permission limits.

## Automatic evaluation
- No severity is assigned; absent module details are common in VMs and unprivileged collection.
- Compare capacity with `/proc/meminfo`; an empty table is not proof that memory hardware is missing.

## Related report items
- [os.total_ram](#item-os.total_ram) — Compare hardware inventory with usable RAM capacity.
- [os.memory_info](#item-os.memory_info) — Compare installed memory with current Linux accounting.

## Checklist
- Compare with `Total RAM Capacity`
- Check hardware monitoring for memory faults.
- Validate capacity after maintenance.
