# Lock Waits

This instruction belongs to report item `activity_locks.lock_waits`. The item is backed by `locks.lock_waits` (SQL query).

## What this item shows
- Blocked sessions and their blocking sessions.
- Lock type, mode, relation, transaction, and query context for current waits.
- Root cause candidates for lock-related latency.

## What to watch
- Long wait age.
- DDL blocking OLTP or OLTP blocking DDL.
- A single blocker holding multiple sessions.
- Blocked autovacuum or maintenance work.

## Common fault causes
- Long transaction holding row or relation locks.
- DDL run during traffic.
- Foreign key checks without supporting indexes.
- Hot-row update contention.

## Checklist
- Identify the root blocker before killing sessions.
- Review blocker xact age and query text.
- Prefer fixing transaction scope or index support over repeated manual kills.
