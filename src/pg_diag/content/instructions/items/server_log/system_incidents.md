# System Incidents From Server Log

This instruction belongs to report item `server_log.system_incidents`. The item consumes the csvlog window collected with `--log-depth-time-min`.

## What this item shows
- Incident-grade capacity, operating-system I/O, checksum, and corruption records, ranked by severity, frequency, and recency.
- Stable SQLSTATE categories work with every `lc_messages` locale. English message signatures add evidence that PostgreSQL may log without a specific SQLSTATE.
- A known application SQLSTATE takes precedence over incident phrases in the message.
  Message fallback matches the start of a server message, not text inside SQL identifiers.
- At most 100 series are emitted. `omitted_series_count` warns when lower-ranked matches were dropped; `count_complete = false` means global collection loss made the count a lower bound.

## What to watch
- `disk_full`, `out_of_memory`, connection/configuration limits, and read/write/fsync failures.
- `checksum_failure`, `data_corruption`, `index_corruption`, or `wal_corruption`: preserve evidence and treat these as urgent until storage and backups are verified.
- A startup `LOG`/`00000` message `invalid record length ... expected at least ... got 0` is an end-of-WAL marker, not standalone corruption evidence. It is retained in `server_log.server_lifecycle`; explicit errors, corruption SQLSTATEs, and nonzero invalid lengths still require review.
- `message_pattern_coverage = structured_sqlstate_only`: non-English messages prevented reliable classification of message-only signatures; this is partial coverage, not proof of absence.

## Common fault causes
- Filesystem exhaustion, inode exhaustion, quota or permissions, failed storage, or a read-only mount.
- Memory overcommit/OOM pressure, exhausted PostgreSQL connection slots, or platform resource limits.
- Hardware/storage faults, torn pages, unsupported copying, or damaged WAL/archive media.

## Automatic evaluation
- Matched incidents require review; FATAL/PANIC raises priority.
- Incomplete collection or locale-limited message classification sets severity to `unknown`.
- A complete empty window proves only that recognized incident signatures were absent during that window.

## Related report items
- [server_log.error_chronology](#item-server_log.error_chronology) — Surrounding error sequence.
- [server_log.log_files_overview](#item-server_log.log_files_overview) — Log volume and rotation state.

## Checklist
- Check free bytes/inodes, kernel/OOM logs, mounts, RAID/cloud-volume health, and PostgreSQL filesystem permissions.
- Do not rebuild or delete corrupted objects before preserving evidence and validating recoverability.
