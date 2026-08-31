# WAL Archiver Failures

This instruction belongs to report item `server_log.archiver_failures`. The item is backed by `server_log.archiver_failures` (trusted Python source) and consumes the csvlog window collected with `--log-depth-time-min`.

## What this item shows
- Failed `archive_command` invocations, collapsed into series with first/last time and repeat counts; the sanitized message carries the command output.
- Any row is incident-grade: un-archived WAL accumulates in `pg_wal` and the WAL archive has a gap until archiving recovers.

## What to watch
- A steadily repeating series: the archiver retries the same segment forever while `pg_wal` grows toward disk exhaustion.
- Failures that started at a deploy or credential rotation: the archive destination changed or lost access.

## Common fault causes
- Expired credentials or rotated keys for the archive destination.
- Full or unreachable archive storage.
- `archive_command` scripts that stopped being executable after an OS update.

## Automatic evaluation
- `high`: any failed invocation in the window.
- `ok`: none.
- An empty result with an incomplete window is reported as unproven, not as absence.

## Related report items
- [wal_io_checkpoints.wal_archiver](#item-wal_io_checkpoints.wal_archiver) — pg_stat_archiver counters for the same process.
- [server_log.log_files_overview](#item-server_log.log_files_overview) — Disk pressure from logs while WAL also grows.

## Checklist
- Fix the archive destination, then watch `pg_stat_archiver.failed_count` stop growing.
- Verify `pg_wal` drains back to its normal size.
- Check PITR coverage across the failure gap before trusting backups.
