# pg_wait_sampling Profile

This instruction belongs to report item `activity_locks.pg_wait_sampling_profile`. The item is backed by `wait.pg_wait_sampling_profile` (SQL query).

## What this item shows
- The top 100 cumulative rows from `pg_wait_sampling_profile`, ordered by sample count.
- PID, event type, event, query ID, samples, and percentage of all current profile samples. Query text is unavailable from this extension view and remains empty.
- Profile data accumulated by the extension rather than a pg_diag snapshot-window delta.

## What to watch
- Dominant lock, I/O, WAL, activity, or client events.
- Query ID zero when profile query tracking is disabled or unavailable.
- Historical PIDs that have exited or been reused; do not treat PID as durable session identity.

## Automatic evaluation
- No severity is assigned because counts depend on the extension's sampling interval, uptime, and last profile reset.
- `sample_share_pct` uses the full profile total before the output is limited to 100 rows.
- Missing optional relation is `unsupported`; an empty result means the visible profile currently has no samples.

## Common fault causes
- Workload contention or latency represented by the dominant event.
- A recent extension restart/reset, disabled sampling, or unavailable query-ID computation.
- An incident outside the cumulative profile's relevant time window.

## Related report items
- [activity_locks.pg_wait_sampling_capabilities](#item-activity_locks.pg_wait_sampling_capabilities) — Verify extension availability and configuration.
- [activity_locks.wait_event_sample_profile](#item-activity_locks.wait_event_sample_profile) — Compare extension history with pg_stat_activity sampling.

## Checklist
- Check the capability item first when this item is unsupported.
- Correlate query IDs with SQL workload, but validate timing because the profile has no per-row timestamp.
- Reset the extension profile only under monitoring policy; pg_diag never resets it.
- Use the pg_diag snapshot wait chart for an explicitly bounded capture window.
