# Autovacuum Runs From Server Log

This instruction belongs to report item `server_log.autovacuum_runs`. The item is backed by `server_log.autovacuum_runs` (trusted Python source) and consumes the csvlog window collected with `--log-depth-time-min`.

## What this item shows
- Automatic vacuum and analyze runs recorded in the server log: time, kind, relation, database, and `elapsed_s` when the first report line carries it.
- csvlog stores an autovacuum report as one multiline record. The bounded log transport now reconstructs the logical record before parsing; this item still renders only the concise first-line chronology rather than the full raw report.
- Runs are visible only when `log_autovacuum_min_duration` is 0 or a positive threshold; `-1` disables the logging entirely.

## What to watch
- The same relation vacuumed again and again: dead-tuple churn outrunning the cost limits.
- Long `elapsed_s` on small tables: cost-based delays or contention, not volume.
- A busy window with zero runs while the item is populated elsewhere: thresholds hiding short runs.

## Common fault causes
- `log_autovacuum_min_duration = -1` hiding autovacuum work from the log.
- Per-table `autovacuum_enabled = off` reloptions left over from migrations.
- Cost limits tuned so low that runs take hours and overlap.

## Automatic evaluation
- `ok`: the item is a chronology; risk evaluation lives in the vacuum items.
- When more runs matched than the listing limit, the summary says only the newest are shown.
- An empty result with an incomplete window is reported as unproven, not as absence.

## Related report items
- [storage_vacuum.table_bloat_candidates](#item-storage_vacuum.table_bloat_candidates) — Where skipped vacuum work ends up.
- [server_log.error_chronology](#item-server_log.error_chronology) — Errors that interrupted maintenance.

## Checklist
- Confirm hot tables appear here regularly; tune per-table thresholds where they do not.
- Compare elapsed times against autovacuum cost settings before raising workers.
