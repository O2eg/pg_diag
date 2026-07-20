# WAL Archive Directory Permissions

This instruction belongs to report item `os.wal_archive_directory_permissions`.
It is backed by local Python source `security.wal_archive_directory_permissions`.

## What this item shows
- Archive destination paths parsed from the command.
- Directory modes that expose or allow modification of archived WAL.

## What to watch
- World access, group write access, or a complex command for which no absolute destination can be inferred.

## Automatic evaluation
- World exposure is `high`; other broad permission findings are `medium`.
- Disabled archiving is `skipped/unknown` as not applicable. `archive_library`, an empty command, or a command without an inferable absolute path produces `unsupported`, never a false pass.

## Common fault causes
- Archive wrapper hides the destination, remote/object storage is used, a relative path depends on service cwd, or archive directory ownership drifted.

## Related report items
- [wal_io_checkpoints.wal_archiver](#item-wal_io_checkpoints.wal_archiver) — Check current archive status and failures.
- [snapshot_delta_workload.wal_archiver_delta](#item-snapshot_delta_workload.wal_archiver_delta) — Measure archive progress during the capture.
- [snapshot_charts_db.wal_growth_rate](#item-snapshot_charts_db.wal_growth_rate) — Compare archive capacity with WAL generation.

## Checklist
- Keep WAL archive directories restricted to PostgreSQL and backup automation.
- Avoid world-readable or writable archive paths.
- Verify command parsing manually for complex archive scripts.
