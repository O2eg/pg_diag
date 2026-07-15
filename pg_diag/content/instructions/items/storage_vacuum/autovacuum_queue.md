# Autovacuum Queue Pressure

This instruction belongs to report item `storage_vacuum.autovacuum_queue`. The item is backed by `vacuum.autovacuum_queue` (SQL query).

## What this item shows
- A bounded current-database ranking of up to 200 tables by dead-tuple, insert-trigger, transaction-ID, and multixact vacuum eligibility.
- Effective global/table thresholds, PostgreSQL 18 maximum threshold, autovacuum enablement, active vacuum state, and last vacuum times.
- Estimates from `pg_stat_all_tables` and `pg_class`; they are not exact row counts.

## What to watch
- Due tables without an active vacuum, especially wraparound eligibility, disabled table autovacuum, or repeatedly growing factors.
- Worker saturation and xmin blockers before treating the threshold itself as the cause.

## Automatic evaluation
- `high`: an XID/multixact freeze threshold is crossed without an active vacuum.
- `medium`: dead-tuple or insert threshold is crossed without an active vacuum.
- A due row already being vacuumed is `ok`; threshold crossing alone does not justify cancellation or manual VACUUM.

## Common fault causes
- Worker saturation, long transactions/slots, disabled or conservative table settings, high DML, or stale statistics estimates.

## Checklist
- Check active Vacuum Progress, xmin blockers, worker slots, and logs.
- Preserve SQL `LIMIT 200`; this is a bounded candidate list, not proof that no lower-ranked table is due.
- Prefer table-level changes only after repeated evidence.
