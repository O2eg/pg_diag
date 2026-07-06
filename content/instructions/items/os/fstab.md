# Filesystem Configuration

This instruction belongs to report item `os.fstab`. The item is backed by `os.fstab` (local host script).

## What this item shows
- Persistent filesystem mount definitions from `/etc/fstab`
- Configured mount options that should survive reboot.

## What to watch
- PGDATA or WAL mount missing from fstab.
- Mount options inconsistent with the storage standard.
- Device names that are unstable across reboot.

## Common fault causes
- Manual mount not persisted.
- Filesystem migration incomplete.
- Cloud block device renamed.
- Wrong mount options copied from another host.

## Checklist
- Compare fstab with currently mounted filesystems.
- Prefer stable UUID/LABEL/device mapper names where appropriate.
- Review options for database storage before reboot.
