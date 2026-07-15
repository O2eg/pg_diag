# Database Wraparound Age

This instruction belongs to report item `storage_vacuum.database_wraparound`. The item is backed by `vacuum.database_wraparound` (SQL query).

## What this item shows
- Cluster database XID and multixact ages relative to autovacuum freeze triggers and vacuum failsafe settings.
- Database OID and frozen horizon identifiers for stable comparison.

## What to watch
- Ages crossing freeze triggers, approaching failsafe, or failing to fall after vacuum activity.
- Rarely connected databases and blockers that prevent horizon advancement.

## Automatic evaluation
- `high`: XID or multixact age reached its configured failsafe threshold.
- `medium`: it crossed the configured autovacuum freeze trigger.
- Percentages are relative to configured operational thresholds, not the raw 32-bit wrap boundary.

## Common fault causes
- Autovacuum backlog/disablement, old transactions or slots, unresolved prepared transactions, and databases not vacuumed regularly.

## Checklist
- Identify blockers before manual vacuum and verify age decreases afterward.
- Treat failsafe findings as urgent; do not reset counters or disable safeguards.
- Include every connectable database in the response plan.
