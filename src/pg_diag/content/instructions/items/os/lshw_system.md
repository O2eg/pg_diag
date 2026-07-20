# System Components

This instruction belongs to report item `os.lshw_system`. The item is backed by `os.lshw_system` (local host script).

## What this item shows
- Hardware or virtual system identity from lshw.
- Vendor, product, serial, and chassis metadata when available.

## What to watch
- Unexpected system model or serial after migration.
- Virtualization type different from expected.
- Missing inventory data due to permissions.

## Common fault causes
- Wrong VM flavor.
- Host replacement not reflected in inventory.
- lshw run without enough privileges.

## Automatic evaluation
- No severity is assigned; inventory must be compared with CMDB or cloud metadata.
- `empty` means no object of this lshw class was returned. `unsupported` means `lshw` was unavailable; stderr warnings indicate potentially incomplete unprivileged inventory.

## Related report items
- [os.os_release](#item-os.os_release) — Compare hardware identity with the installed OS.
- [os.cpu_info](#item-os.cpu_info) — Inspect CPU topology for the same host.
- [os.total_ram](#item-os.total_ram) — Inspect memory capacity for the same host.

## Checklist
- Compare with CMDB or cloud instance metadata.
- Confirm the report was collected on the intended host.
- Use this only as inventory evidence, not performance proof.
