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

## Checklist
- Compare with CMDB or cloud instance metadata.
- Confirm the report was collected on the intended host.
- Use this only as inventory evidence, not performance proof.
