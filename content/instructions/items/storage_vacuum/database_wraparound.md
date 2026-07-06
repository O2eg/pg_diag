# Database Wraparound Age

This instruction belongs to report item `storage_vacuum.database_wraparound`. The item is backed by `vacuum.database_wraparound` (SQL query).

## What this item shows
- Transaction ID and multixact age by database.
- Distance to wraparound-related limits.
- Whether any database needs urgent vacuum attention.

## What to watch
- Age approaching autovacuum_freeze_max_age or multixact limits.
- Databases not regularly vacuumed.
- High age after bulk load or long outage.

## Common fault causes
- Autovacuum disabled or lagging.
- Long transactions prevent freezing.
- Database rarely connected but still aging.
- Prepared transactions retaining horizons.

## Checklist
- Treat high wraparound age as urgent.
- Vacuum oldest databases first.
- Find and clear blockers before expecting progress.
