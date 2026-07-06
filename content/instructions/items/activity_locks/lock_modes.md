# Lock Mode Counts

This instruction belongs to report item `activity_locks.lock_modes`. The item is backed by `locks.lock_modes` (SQL query).

## What this item shows
- Current lock counts by lock mode and granted state.
- Which lock modes are accumulating even when no active wait is shown.
- Relation between granted locks and waiting locks.

## What to watch
- Many ungranted locks.
- AccessExclusiveLock during business traffic.
- Lock count spike on one database or relation.

## Common fault causes
- Schema migration.
- Bulk maintenance.
- Long transactions.
- High concurrency touching same objects.

## Checklist
- Use this as a summary, then inspect `Lock Waits` for blockers.
- Check for DDL windows and migrations.
- Compare with session and long transaction items.
