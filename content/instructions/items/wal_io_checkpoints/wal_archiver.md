# WAL Archiver

This instruction belongs to report item `wal_io_checkpoints.wal_archiver`. The item is backed by `wal.archiver` (SQL query).

## What this item shows
- Archive command success/failure counters and last archived or failed WAL.
- Approximate pending WAL segment context where available.
- Whether PITR/backup archive pipeline is healthy.

## What to watch
- Failed archive count increasing.
- Last failed WAL newer than last archived WAL.
- Pending archive backlog.

## Common fault causes
- archive_command failure.
- Archive destination full or slow.
- Permission or network issue.
- WAL generation faster than archive throughput.

## Checklist
- Check PostgreSQL logs for archive_command stderr.
- Validate archive destination capacity.
- Do not ignore failures if backups or PITR rely on archives.
