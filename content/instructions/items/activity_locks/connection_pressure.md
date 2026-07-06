# Connection Pressure

This instruction belongs to report item `activity_locks.connection_pressure`. The item is backed by `activity.connection_pressure` (SQL query).

## What this item shows
- Current connections compared with `max_connections` and reserved connection slots.
- Counts of active, idle, idle-in-transaction, and waiting sessions.
- How much connection headroom remains for applications and administration.

## What to watch
- Used percentage close to ordinary or total connection limit.
- Many idle sessions consuming connection slots.
- Waiting sessions while connection count is high.

## Common fault causes
- Connection pool size too large.
- Connection leak or clients not closing sessions.
- Slow transactions keeping backends occupied.
- Application retry storm.

## Checklist
- Keep emergency admin access available.
- Compare application pool limits with PostgreSQL limits.
- Identify which application_name or client group owns the growth.
- Fix pool/leak behavior before raising max_connections.
