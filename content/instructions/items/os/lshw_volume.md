# Disk Partitions And Volumes

This instruction belongs to report item `os.lshw_volume`. The item is backed by `os.lshw_volume` (local host script).

## What this item shows
- Partition and volume inventory from lshw.
- Volume layout below mounted filesystems.

## What to watch
- Unexpected partition size or layout.
- Missing volume after storage change.
- Database path on an unintended volume.

## Common fault causes
- Filesystem not expanded after disk resize.
- Wrong volume mounted.
- Partition table drift.

## Checklist
- Compare with `Mounted Filesystems` and `Filesystem Usage`
- Check volume size before blaming PostgreSQL growth.
- Validate storage layout after maintenance.
