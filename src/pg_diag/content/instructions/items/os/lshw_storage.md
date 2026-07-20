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

## Automatic evaluation
- No severity is assigned without an expected storage-controller baseline.
- Empty/partial output does not prove that storage is absent; virtual and unprivileged environments commonly hide controller details.

## Related report items
- [os.lshw_disk](#item-os.lshw_disk) — Inspect disks attached to each storage controller.
- [os.lshw_volume](#item-os.lshw_volume) — Inspect partitions and logical volumes.
- [snapshot_charts_os.os_disk_latency](#item-snapshot_charts_os.os_disk_latency) — Compare hardware topology with observed latency.

## Checklist
- Compare with disk and mount evidence.
- Check controller driver/firmware during I/O incidents.
- Confirm storage tier matches the database role.
