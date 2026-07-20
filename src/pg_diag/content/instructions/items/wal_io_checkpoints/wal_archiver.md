# WAL Archiver

This instruction belongs to report item `wal_io_checkpoints.wal_archiver`. The item is backed by `wal.archiver` (SQL query).

## What this item shows
- Cluster archiver mode/target posture, success/failure counters, last archived/failed files and times, reset time, current primary WAL filename, and configured segment size.
- A same-timeline filename distance calculated with the actual `wal_segment_size`; this is context, not an exact archive backlog.
- On a standby the current filename/distance is null because PostgreSQL cannot safely derive it during recovery; `archive_mode=always` can still archive received WAL.

## What to watch
- The latest recorded attempt failed, archiving is enabled without a command/library, or failure counts increase between captures.
- WAL accumulation in `pg_wal` and archive destination health.
- Timeline changes, which intentionally invalidate filename-distance arithmetic.

## Automatic evaluation
- `medium`: archive mode is enabled without a configured target, or the newest recorded archive event is a failure.
- Historical failures followed by a newer success do not assign severity.
- `archive_mode=off` is not automatically a failure because PITR requirements are deployment-specific.

## Common fault causes
- Command/library failure, full/slow/unreachable target, permissions, duplicate-file protection, network outage, or WAL generation exceeding throughput.
- Some command termination paths restart the archiver without incrementing `failed_count`; logs remain authoritative.

## Related report items
- [snapshot_delta_workload.wal_archiver_delta](#item-snapshot_delta_workload.wal_archiver_delta) — Measure archive progress during the capture.
- [snapshot_delta_workload.wal_activity_delta](#item-snapshot_delta_workload.wal_activity_delta) — Compare archived segments with generated WAL.
- [os.wal_archive_directory_permissions](#item-os.wal_archive_directory_permissions) — Check archive-directory access and ownership.

## Checklist
- Inspect PostgreSQL logs and the local `.ready` archive status, not filename distance alone.
- Validate destination capacity, retention, and restore usability.
- PostgreSQL does not guarantee archive completion order, especially around promotion/recovery.
- Do not force a WAL switch or reset statistics merely to run diagnostics.
