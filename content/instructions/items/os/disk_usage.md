# Filesystem Usage

This instruction belongs to report item `os.disk_usage`. The item is backed by `os.disk_usage` (local host script).

## What this item shows
- Filesystem capacity, used/free bytes, and utilization percentage from `df`.
- The artifact stores exact bytes and a raw percentage; the table applies adaptive IEC display units.
- Which mount points are close to full at collection time.

## What to watch
- Data, WAL, archive, backup, temp, or log filesystems above safe utilization thresholds.
- Filesystems with very little free byte capacity.
- Unexpected PostgreSQL paths on root filesystem.

## Common fault causes
- WAL archive backlog.
- Log growth.
- Temporary file spill.
- Autovacuum or bloat increasing data size.
- Backups left on database storage.

## Automatic evaluation
- No fixed utilization threshold is assigned automatically because reserved blocks, growth rate, filesystem size, and operational headroom differ by environment.
- This item uses byte capacity from `df -P -B1`; inode exhaustion must be checked separately.

## Checklist
- Identify mount points that contain PGDATA, WAL, logs, archives, and backups.
- Free or expand space before restarting write-heavy jobs.
- Correlate full filesystems with WAL archiver and temp file evidence.
