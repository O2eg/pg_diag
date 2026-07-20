# Session States

This instruction belongs to report item `activity_locks.session_states`. The item is backed by `activity.session_states` (SQL query).

## What this item shows
- An instantaneous count of client sessions across all databases, grouped by database, `application_name`, and PostgreSQL state.
- Maximum open-transaction age in seconds for each populated state group.
- Zero-count rows for known states when no session currently has that state. pg_diag's own backend is excluded.

## What to watch
- An application dominating active or total session counts.
- Any sustained `idle in transaction` or `idle in transaction (aborted)` population.
- Transaction age much longer than the application's expected request or batch duration.

## Automatic evaluation
- This summary does not assign severity because state counts are workload-dependent and instantaneous.
- State and wait are separate dimensions: `active` does not mean CPU use, and this item does not report waiting-session counts.
- Other users' activity details require sufficient statistics visibility; without it, group attribution can be partial.

## Common fault causes
- Connection-pool bursts or background-job fan-out.
- Slow queries increasing the active population.
- Missing commit or rollback paths.

## Related report items
- [activity_locks.wait_events](#item-activity_locks.wait_events) — Separate active work from instrumented waits.
- [activity_locks.idle_in_transaction](#item-activity_locks.idle_in_transaction) — Inspect sessions retaining transactions while idle.
- [snapshot_charts_db.activity_sessions_by_state](#item-snapshot_charts_db.activity_sessions_by_state) — Compare the point-in-time table with the session-state trend.

## Checklist
- Compare application groups with configured pool limits.
- Use `Active Wait Events` to separate running work from waits.
- Use `Idle In Transaction Over 1 Minute` for actionable session details.
- Zero counts are valid observations; collection `error` or `unsupported` is unavailable evidence.
