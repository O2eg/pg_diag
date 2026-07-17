# SLRU Statistics

This instruction belongs to report item `wal_io_checkpoints.slru_statistics`. The item is backed by `slru.stat_slru` (SQL query).

## What this item shows
- Cluster-wide cumulative SLRU block hits/reads/accesses, hit percentage, writes, flushes, truncations, and reset age by SLRU area.
- Activity for transaction status, subtransactions, multixacts, notifications, commit timestamps, and other extension-defined areas.

## What to watch
- Read/write deltas concentrated in one SLRU, low hit percentage with meaningful access volume, or stalled truncation combined with old horizons.
- Multixact activity around foreign-key locking and subtransaction activity from nested savepoints.

## Automatic evaluation
- No automatic severity: raw cumulative counts and cache ratios require rates, workload type, and reset age.

## Common fault causes
- Deep subtransactions, heavy row locking/foreign keys, LISTEN/NOTIFY churn, old xmin/multixact horizons, or a working set larger than the SLRU cache.

## Related report items
- [snapshot_delta_workload.slru_activity_delta](#item-snapshot_delta_workload.slru_activity_delta) — Measure SLRU changes during the capture.
- [activity_locks.long_transactions](#item-activity_locks.long_transactions) — Investigate transaction-age pressure.
- [storage_vacuum.database_wraparound](#item-storage_vacuum.database_wraparound) — Check wraparound age associated with transaction SLRUs.

## Checklist
- Compare deltas using the same `stats_reset` value.
- Interpret `hit_pct` only when `block_accesses` is material; it is an SLRU cache ratio, not an OS disk-cache ratio.
- Correlate with locks, long transactions, wraparound horizons, and OS I/O.
- Do not reset SLRU statistics during diagnosis.
