# Wait Event Sample Profile

This instruction belongs to report item `activity_locks.wait_event_sample_profile`. The item is backed by `activity.wait_sample_profile` (snapshot metric).

## What this item shows
- Sampled wait events from repeated pg_stat_activity snapshots.
- Up to 12 wait groups with the highest average active-session count in each interval.
- A timestamped stacked chart of wait event type, event, and query ID.
- Short-window wait profile without requiring pg_wait_sampling.

## What to watch
- One wait type dominates samples.
- Lock, I/O, WAL, or Client waits during incident window.
- Too few samples for intermittent waits.
- `CPU` means an active session had no reported wait event; it is not proof that the session was executing on CPU.

## Common fault causes
- Lock contention.
- Storage latency.
- WAL sync pressure.
- Slow clients.
- Capture window missed the event.

## Checklist
- Match wait samples to timestamped workload charts.
- Use lock and SQL sections for the dominant wait group.
- Repeat with longer duration for intermittent incidents.
