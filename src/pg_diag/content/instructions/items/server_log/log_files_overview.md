# Server Log Files Overview

This instruction belongs to report item `server_log.log_files_overview`. The item is backed by `server_log.log_files_overview` (trusted Python source) and needs only `pg_ls_logdir()` — it works even when the log content itself is unreadable for the collector.

## What this item shows
- csvlog files from `pg_ls_logdir()`: size, last modification, whether the file falls into the requested window, and which file is currently active.
- Findings about rotation health: rotation disabled (`log_rotation_age` and `log_rotation_size` both 0), a runaway active file, or excessive total log volume.

## What to watch
- `in_window = false` on every file but the active one: the requested depth exceeds what rotation retained.
- An active file far larger than the rotation size: the collector stays cheap thanks to bounded reads, but rotation is broken.
- Total volume worth many gigabytes: log retention nobody configured.

## Common fault causes
- Rotation disabled during an incident investigation and never re-enabled.
- `log_truncate_on_rotation = off` with a cyclic `log_filename` pattern appending forever.
- Verbose logging (statements, connections) multiplying volume.

## Automatic evaluation
- `high`: rotation disabled, or the active csvlog exceeds 1 GiB.
- `medium`: total csvlog volume exceeds 10 GiB.
- `ok`: otherwise.

## Related report items
- [server_log.error_chronology](#item-server_log.error_chronology) — The content read from these files.
- [server_log.top_errors](#item-server_log.top_errors) — What fills these files with volume.

## Checklist
- Re-enable rotation and set retention for rotated files.
- Trim verbose logging settings that inflate volume without diagnostic value.
