# SLRU Statistics

This instruction belongs to report item `wal_io_checkpoints.slru_statistics`. The item is backed by `slru.stat_slru` (SQL query).

## What this item shows
- SLRU cache counters by SLRU area.
- Reads, writes, flushes, truncates, and hit rates for transaction-related storage.
- Whether subtransaction, multixact, notify, or commit-status areas are active.

## What to watch
- High SLRU reads or writes for one area.
- Multixact activity during FK-heavy workload.
- Subtrans activity from nested transactions.

## Common fault causes
- Deep subtransactions.
- High foreign-key lock/check activity.
- LISTEN/NOTIFY churn.
- Old transaction horizons delaying truncation.

## Checklist
- Identify which SLRU area is hot.
- Correlate multixact activity with locks and FK workload.
- Check xmin and long transactions when truncation is delayed.
