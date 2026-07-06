# pg_wait_sampling Profile

This instruction belongs to report item `activity_locks.pg_wait_sampling_profile`. The item is backed by `wait.pg_wait_sampling_profile` (SQL query).

## What this item shows
- Rows from pg_wait_sampling_profile when pg_wait_sampling is installed.
- Historical sampled waits by PID, event type, event, queryid, and sample count.
- Wait profile beyond the current pg_stat_activity instant.

## What to watch
- High sample count for one wait event or queryid.
- Profile unavailable because relation does not exist.
- Old samples that do not match current incident window.

## Common fault causes
- Lock contention.
- I/O latency.
- WAL pressure.
- Extension not installed.
- Profile reset or sampling disabled.

## Checklist
- Check capability item first when unavailable.
- Correlate queryid with SQL workload.
- Reset or window samples intentionally when measuring a specific incident.
