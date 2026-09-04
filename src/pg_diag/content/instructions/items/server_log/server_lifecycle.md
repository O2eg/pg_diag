# Server Lifecycle From Server Log

This instruction belongs to report item `server_log.server_lifecycle`. The item consumes the csvlog window collected with `--log-depth-time-min`.

## What this item shows
- Startup, readiness, smart/fast/immediate shutdown, backend crash, crash recovery, promotion, and configuration reload/startup errors.
- `recovery_wal_end` retains the startup zero-length end-of-WAL marker. It is observational by itself; check the surrounding recovery and readiness sequence for failures.
- Up to 100 newest event series; repeated adjacent messages are collapsed with occurrence and first/last timestamps.
- PostgreSQL localizes these messages, so the item is unsupported when `lc_messages` is not C/POSIX/English rather than claiming a false empty result.

## What to watch
- Unclean shutdown or backend crash followed by recovery.
- Promotion/timeline events that do not match the expected failover chronology.
- Reload/startup errors followed by no readiness marker.

## Common fault causes
- Host or container restart, OOM kill, storage failure, operator action, HA failover, or invalid configuration.
- A crashing extension/backend, postmaster child failure, or forced immediate shutdown.

## Automatic evaluation
- Clean lifecycle markers are observational; crash, unclean shutdown, startup, or configuration failures are high priority.
- `omitted_series_count` reports the fixed 100-row limit; incomplete collection makes chronology and counts lower bounds.

## Related report items
- [server_log.crash_recovery_events](#item-server_log.crash_recovery_events) — Existing focused crash/recovery compatibility item.
- [server_log.replication_events](#item-server_log.replication_events) — Failover and replication transport evidence.

## Checklist
- Reconstruct the sequence by timestamp and compare it with service-manager, kernel, container, and HA-controller logs.
- Confirm that every intended startup or promotion reaches readiness.
