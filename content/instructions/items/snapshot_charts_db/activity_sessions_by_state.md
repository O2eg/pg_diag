# Sessions By State

This instruction belongs to report item `snapshot_charts_db.activity_sessions_by_state`. The item is backed by `activity.sessions_by_state` (snapshot metric).

## What this item shows
- Session state counts over time.
- Active, idle, idle-in-transaction, and waiting session trends.

## What to watch
- Active sessions rising with latency.
- Idle-in-transaction appearing during capture.
- Waiting sessions increasing.

## Common fault causes
- Pool burst.
- Blocked workload.
- Open transactions left idle.
- Slow client behavior.

## Checklist
- Correlate with lock waits and connection pressure.
- Identify application_name owners.
- Use repeated capture for intermittent session spikes.
