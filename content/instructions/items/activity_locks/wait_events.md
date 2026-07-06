# Active Wait Events

This instruction belongs to report item `activity_locks.wait_events`. The item is backed by `activity.wait_events` (SQL query).

## What this item shows
- Active sessions grouped by wait event type, wait event, database, and query_id.
- Current wait concentration visible in pg_stat_activity.
- Whether active work is blocked on locks, I/O, WAL, client, or extension waits.

## What to watch
- One wait event dominates active sessions.
- Lock or LWLock waits during application latency.
- Client waits that may indicate slow consumers rather than slow database work.

## Common fault causes
- Lock contention.
- Storage latency.
- WAL flush pressure.
- Client backpressure.
- Extension or background worker waits.

## Checklist
- Start with the largest wait group.
- Map query_id and application_name to top SQL and application owner.
- Use repeated snapshots if waits are intermittent.
