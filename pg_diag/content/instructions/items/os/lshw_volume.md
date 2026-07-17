# Disk Partitions And Volumes

This instruction belongs to report item `os.lshw_volume`. The item is backed by `os.lshw_volume` (local host script).

## What this item shows
- Partition and volume inventory from lshw, with normalized `lsblk --json` fallback when lshw has no usable volume rows.
- Volume layout below mounted filesystems.
- Size and available capacity are exact bytes; filesystem use is a numeric percentage.

## What to watch
- Unexpected partition size or layout.
- Missing volume after storage change.
- Database path on an unintended volume.

## Common fault causes
- Filesystem not expanded after disk resize.
- Wrong volume mounted.
- Partition table drift.

## Automatic evaluation
- No severity is assigned without an expected partition/LVM layout.
- `unsupported` means neither usable lshw data nor the `lsblk` fallback was available. Older util-linux versions use a reduced fallback column set.

## Related report items
- [os.mounts](#item-os.mounts) — Map partitions and volumes to active mount points.
- [os.disk_usage](#item-os.disk_usage) — Inspect capacity for those filesystems.

## Checklist
- Compare with `Mounted Filesystems` and `Filesystem Usage`
- Check volume size before blaming PostgreSQL growth.
- Validate storage layout after maintenance.
