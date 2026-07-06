# Session States

This instruction belongs to report item `activity_locks.session_states`. The item is backed by `activity.session_states` (SQL query).

## What this item shows
- Current backend counts grouped by session state and application.
- Whether sessions are active, idle, idle in transaction, or waiting.
- Maximum transaction age for state groups.

## What to watch
- Large active count during latency incidents.
- Idle-in-transaction count above zero.
- One application_name dominating the session population.

## Common fault causes
- Connection pool burst.
- Slow query pileup.
- Clients leaving transactions open.
- Background job fan-out.

## Checklist
- Group by application_name first.
- Inspect representative active and idle-in-transaction PIDs.
- Check whether high active count aligns with CPU, I/O, or lock waits.
