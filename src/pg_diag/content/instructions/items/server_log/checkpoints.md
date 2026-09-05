# Checkpoints From Server Log

This instruction belongs to report item `server_log.checkpoints`. The item is backed by `server_log.checkpoints` (trusted Python source) and consumes the csvlog window collected with `--log-depth-time-min`.

## What this item shows
- `checkpoint`/`restartpoint` starting and complete events: trigger reason, buffers written, and `write`/`sync`/`total` seconds from the complete line.
- Requires `log_checkpoints = on` (the default since PostgreSQL 15).

## What to watch
- Starting reason `wal`: WAL pressure is driving checkpoints off schedule — the summary flags this as `medium`.
- `force`/`immediate` alone can come from an explicit CHECKPOINT or a backup and do not prove WAL volume pressure.
- Large `sync_s` relative to `write_s`: storage flush latency, not dirty-buffer volume.
- Restartpoints on a standby lagging far behind checkpoints on the primary.

## Common fault causes
- `max_wal_size` too small for burst write load.
- Bulk loads or index builds generating WAL spikes.
- Slow fsync on network or overloaded storage.

## Automatic evaluation
- `medium`: at least one checkpoint in the window started for `wal` reasons.
- `ok`: no WAL-triggered checkpoint in the listed events; timed and explicit starts do not raise this flag.
- The newest 200 event series are listed. `omitted_series_count` identifies a capped result;
  `count_complete` and the first/last event times preserve count and window coverage.
- An empty result with an incomplete window is reported as unproven, not as absence.

## Related report items
- [wal_io_checkpoints.bgwriter](#item-wal_io_checkpoints.bgwriter) — Counter view of the same write pressure.
- [server_log.log_files_overview](#item-server_log.log_files_overview) — Log rotation health for this evidence.

## Checklist
- Review `max_wal_size` when WAL-triggered checkpoints repeat under normal load.
- Investigate storage when `sync_s` dominates `total_s`.
