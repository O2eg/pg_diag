# Idle In Transaction Over 1 Minute

This instruction belongs to report item `activity_locks.idle_in_transaction`. The item is backed by `activity.idle_in_transaction` (SQL query).

## What this item shows
- Sessions idle inside an open transaction for more than one minute.
- User, application, client, xact age, and last query for idle transactions.
- Potential xmin and lock retention sources.

## What to watch
- Any row in this item on OLTP systems.
- High xact age or backend_xmin age.
- Idle transaction from application pool connections.

## Common fault causes
- Application did not commit or rollback.
- Client disconnected without cleanup.
- Pooler used in session mode with open transactions.
- Interactive psql session left open.

## Checklist
- Confirm owner and last query.
- Terminate stale sessions when safe.
- Fix application code or pooler behavior.
- Consider idle_in_transaction_session_timeout.
