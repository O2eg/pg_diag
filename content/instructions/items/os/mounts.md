# Mounted Filesystems

This instruction belongs to report item `os.mounts`. The item is backed by `os.mounts` (local host script).

## What this item shows
- Currently mounted filesystems and mount options.
- Actual runtime storage layout used by the collector host.

## What to watch
- Mounts differ from `/etc/fstab`
- Read-only or unexpected mount options on database paths.
- Database directories mounted on slower or temporary storage.

## Common fault causes
- Manual remount.
- Failed mount at boot.
- Storage failover or device replacement.
- Container bind mount hiding host layout.

## Checklist
- Compare with fstab and disk usage.
- Confirm PGDATA, WAL, logs, and temp directories are on intended mounts.
- Check mount options before diagnosing I/O performance.
