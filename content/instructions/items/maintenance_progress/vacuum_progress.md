# Vacuum Progress

This instruction belongs to report item `maintenance_progress.vacuum_progress`. The item is backed by `progress.vacuum` (SQL query).

## What this item shows
- Live progress rows for VACUUM and autovacuum operations.
- Current phase, heap blocks scanned/vacuumed, index vacuuming, and dead tuple context where available.
- Which relation is being vacuumed right now.

## What to watch
- Vacuum stuck in one phase.
- Very slow heap scan on large relation.
- Autovacuum running on hot table during incident.

## Common fault causes
- Large bloated table.
- I/O pressure.
- Index cleanup cost.
- Lock waits or conflicting workload.

## Checklist
- Confirm relation and command owner.
- Check locks if phase appears stalled.
- Compare with autovacuum queue and table size before canceling.
