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

## Checklist
- Compare with `Total RAM Capacity`
- Check hardware monitoring for memory faults.
- Validate capacity after maintenance.
