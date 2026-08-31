# Crash And Recovery Events

This instruction belongs to report item `server_log.crash_recovery_events`. The item is backed by `server_log.crash_recovery_events` (trusted Python source) and consumes the csvlog window collected with `--log-depth-time-min`.

## What this item shows
- Records whose message carries crash, recovery, or corruption markers: `terminated by signal`, `was not properly shut down`, `automatic recovery in progress`, `redo starts at`, `invalid page`, `terminating any other active server processes`.
- Up to 200 newest events with severity, process, backend type, user, and database.

## What to watch
- `terminated by signal 9`: almost always the kernel OOM killer.
- `invalid page`: on-disk corruption evidence; treat as a data-integrity incident.
- `was not properly shut down` plus `automatic recovery in progress`: the server crashed and replayed WAL; ask why.

## Common fault causes
- Memory overcommit and OOM kills under load spikes.
- Storage failures or unsafe filesystem settings.
- Manual `kill -9` of backends instead of `pg_terminate_backend`.

## Automatic evaluation
- `high`: any event is present; every row here is incident-grade.
- `ok`: the collected window contains no crash or recovery markers.

## Related report items
- [server_log.error_chronology](#item-server_log.error_chronology) — Surrounding errors in time order.

## Checklist
- Correlate events with kernel logs (OOM) and storage alerts.
- After `invalid page`, plan a corruption check before trusting backups taken after the event.
- Confirm crash recovery completed and replication caught up.
