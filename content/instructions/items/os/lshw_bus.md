# Buses And Interfaces

This instruction belongs to report item `os.lshw_bus`. The item is backed by `os.lshw_bus` (local host script).

## What this item shows
- Hardware buses and interface inventory.
- PCI/firmware topology relevant to storage and network devices.

## What to watch
- Missing expected bus devices.
- Unexpected virtual bus layout.
- Devices attached through slower interface than expected.

## Common fault causes
- Driver or firmware issue.
- VM configuration change.
- Hardware replacement.

## Checklist
- Use with network/storage lshw sections for device-specific checks.
- Confirm device topology after hardware or VM changes.
- Escalate missing hardware to platform team.
