# Autovacuum Queue Pressure

This instruction belongs to report item `storage_vacuum.autovacuum_queue`. The item is backed by `vacuum.autovacuum_queue` (SQL query).

## What this item shows
- Tables with dead tuple pressure relative to autovacuum thresholds.
- Estimated overdue factor and vacuum/analyze need for user tables.
- Which relations may need autovacuum attention.

## What to watch
- High autovacuum_overdue_factor.
- Large n_dead_tup on frequently updated tables.
- Tables repeatedly near threshold.

## Common fault causes
- Autovacuum workers saturated.
- Per-table thresholds too high.
- Long transactions blocking cleanup.
- Write-heavy workload.

## Checklist
- Prioritize high-overdue large tables.
- Check long transactions and xmin blockers.
- Tune table-level autovacuum settings when needed.
