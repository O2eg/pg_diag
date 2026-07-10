# Lock Mode Counts

This instruction belongs to report item `activity_locks.lock_modes`. The item is backed by `locks.lock_modes` (SQL query).

## What this item shows
- An instantaneous count by lock type, mode, and granted state.
- Locks whose target belongs to the connected database plus database-independent locks held or requested by its sessions.
- Prepared-transaction locks with a current-database target; pg_diag's own locks are excluded.

## What to watch
- Ungranted requests, especially restrictive relation-lock modes.
- Unexpected `AccessExclusiveLock` during business traffic.
- Large lock populations that align with long transactions.

## Automatic evaluation
- `medium`: one or more rows contain ungranted lock requests.
- Granted lock counts are informational because normal transactions routinely hold many locks.
- Counts are point-in-time and `pg_locks` is not a historical or perfectly atomic cluster snapshot.

## Common fault causes
- Schema migrations or bulk maintenance.
- Long transactions and high-concurrency access to the same objects.
- Advisory-lock coordination or prepared transactions.

## Checklist
- Use `Lock Waits` to identify exact blockers and wait duration.
- Check DDL and maintenance windows and compare with long transactions.
- Do not infer a blocker from mode counts alone.
- Empty means no matching lock row after excluding pg_diag itself; collection error is unavailable evidence.
