# Wait Event Sample Profile

This instruction belongs to report item `activity_locks.wait_event_sample_profile`. The item is backed by `activity.wait_sample_profile` (snapshot metric).

## What this item shows
- Repeated bounded samples of active PostgreSQL processes during snapshots mode.
- A stacked-column chart of up to 12 groups with the highest average active-session count per interval.
- Database, wait event, and query-ID attribution without requiring `pg_wait_sampling`.

## What to watch
- A wait type that repeatedly dominates adjacent samples.
- Lock, I/O, WAL, or client waits aligned with an incident window.
- Sparse sampling that can miss short waits or change the bounded Top-N membership between snapshots.

## Automatic evaluation
- The chart is observational and does not assign severity.
- `Not waiting / Active without wait event` is not proof of CPU execution; the process can be runnable or delayed outside a PostgreSQL wait instrument.
- Each source sample is limited to 100 groups, then the metric keeps 12 interval groups. Cross-user details require statistics visibility.

## Common fault causes
- Lock contention, storage latency, WAL pressure, or slow clients.
- CPU saturation for repeated active-without-wait samples.
- A capture interval too coarse or a capture window outside the incident.

## Related report items
- [activity_locks.wait_events](#item-activity_locks.wait_events) — Compare sampled groups with the current wait table.
- [activity_locks.lock_waits](#item-activity_locks.lock_waits) — Resolve persistent lock waits to blockers.
- [snapshot_charts_os.os_cpu_utilization](#item-snapshot_charts_os.os_cpu_utilization) — Separate CPU saturation from PostgreSQL wait states.

## Checklist
- Correlate chart columns with host CPU/I/O and SQL delta charts at the same timestamps.
- Inspect `Lock Waits` or SQL items for the dominant group.
- Repeat with a shorter interval or longer duration when the event is intermittent.
- No points means no active groups were captured or the metric source was unavailable; inspect collection status before concluding the system was idle.
