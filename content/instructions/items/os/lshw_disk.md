# Disks And SSDs

This instruction belongs to report item `os.lshw_disk`. The item is backed by `os.lshw_disk` (local host script).

## What this item shows
- Physical or virtual disk inventory, model, size, serial, and capabilities where visible.
- Device identity context for database storage.

## What to watch
- Unexpected disk model, size, rotational flag, or serial.
- Missing disks or disks on wrong tier.
- Inventory unavailable due to permissions.

## Common fault causes
- Storage migration incomplete.
- Wrong volume attached.
- Cloud disk resized without filesystem expansion.

## Checklist
- Map disks to mounts used by PostgreSQL.
- Compare disk identity with storage monitoring.
- Confirm WAL/data/archive devices are on intended storage.
