# Sessions By State

This instruction belongs to report item `snapshot_charts_db.activity_sessions_by_state`. The item is backed by `activity.sessions_by_state` (snapshot metric).

## What this item shows
- Per-database session state counts over time for all databases.
- Active, idle, idle-in-transaction, aborted, fastpath, and disabled state trends.

## What to watch
- Active sessions rising with latency.
- Idle-in-transaction appearing during capture.
- Active sessions increasing; wait status itself is not represented by `state`.

## Common fault causes
- Pool burst.
- Blocked workload.
- Open transactions left idle.
- Slow client behavior.

## Automatic evaluation
- This chart is informational and partitions every series by database and state.
- A session can be active and waiting simultaneously; use wait-profile and lock items for waits.

## Related report items
- [activity_locks.session_states](#item-activity_locks.session_states) — Inspect current sessions and application ownership.
- [activity_locks.lock_waits](#item-activity_locks.lock_waits) — Resolve active waiting sessions to blockers.
- [activity_locks.connection_pressure](#item-activity_locks.connection_pressure) — Compare state counts with connection capacity.

## Checklist
- Correlate with lock waits and connection pressure.
- Identify application_name owners.
- Use repeated capture for intermittent session spikes.
