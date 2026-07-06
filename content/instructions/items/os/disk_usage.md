# Filesystem Usage

This instruction belongs to report item `os.disk_usage`. The item is backed by `os.disk_usage` (local host script).

## What this item shows
- Filesystem capacity and used/free space from `df`
- Which mount points are close to full at collection time.

## What to watch
- Data, WAL, archive, backup, temp, or log filesystems above safe utilization thresholds.
- Filesystems with very little free inode or byte capacity.
- Unexpected PostgreSQL paths on root filesystem.

## Common fault causes
- WAL archive backlog.
- Log growth.
- Temporary file spill.
- Autovacuum or bloat increasing data size.
- Backups left on database storage.

## Checklist
- Identify mount points that contain PGDATA, WAL, logs, archives, and backups.
- Free or expand space before restarting write-heavy jobs.
- Correlate full filesystems with WAL archiver and temp file evidence.
