# Storage Controllers

This instruction belongs to report item `os.lshw_storage`. The item is backed by `os.lshw_storage` (local host script).

## What this item shows
- Storage controller inventory and driver context.
- Controller-level evidence for disks used by PostgreSQL.

## What to watch
- Unexpected controller type or driver.
- Controller missing after host migration.
- Virtual storage controller not matching performance tier.

## Common fault causes
- VM storage adapter change.
- Driver issue.
- Hardware replacement.

## Checklist
- Compare with disk and mount evidence.
- Check controller driver/firmware during I/O incidents.
- Confirm storage tier matches the database role.
