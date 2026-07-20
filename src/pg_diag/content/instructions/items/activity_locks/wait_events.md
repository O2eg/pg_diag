# Active Wait Events

This instruction belongs to report item `activity_locks.wait_events`. The item is backed by `activity.wait_events` (SQL query).

## What this item shows
- One instantaneous cluster-wide sample of active PostgreSQL processes, grouped by database, application, wait event, query ID, and normalized query text.
- At most 100 groups, ordered by current session count; pg_diag's own backend is excluded.
- `Not waiting / Active without wait event` when PostgreSQL reports an active process with no wait event.

## What to watch
- Lock, I/O, WAL, or extension waits concentrated in one query or application.
- A large `Not waiting` group during CPU saturation, while remembering it is not proof that those processes were on CPU.
- Missing query IDs or text, which can result from permissions or disabled query-ID computation.

## Automatic evaluation
- No severity is assigned from a single wait sample because transient waits are normal and thresholds are workload-specific.
- Accurate cross-user query and wait details normally require `pg_read_all_stats` or `pg_monitor`.
- The SQL limit bounds collector memory; groups outside the current top 100 are not represented.

## Common fault causes
- Lock contention, storage latency, or WAL flush pressure.
- Client backpressure or synchronous replication.
- CPU saturation, scheduler delay, or active computation for rows with no wait event.

## Related report items
- [activity_locks.lock_waits](#item-activity_locks.lock_waits) — Resolve lock waits to blocker and blocked sessions.
- [activity_locks.wait_event_sample_profile](#item-activity_locks.wait_event_sample_profile) — Check whether the wait persists across the snapshot window.
- [sql_workload.top_sql_by_total_time](#item-sql_workload.top_sql_by_total_time) — Look for cumulative SQL associated with the wait class.

## Checklist
- Start with the largest group and correlate its timestamp with host and workload evidence.
- Use `Lock Waits` for lock blockers and SQL workload items for query history.
- Use the snapshot chart when the event is intermittent.
- An empty table means no other active process was observed; an error means the sample is unavailable.
