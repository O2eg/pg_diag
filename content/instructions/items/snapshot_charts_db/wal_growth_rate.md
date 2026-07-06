# WAL Growth Rate

This instruction belongs to report item `snapshot_charts_db.wal_growth_rate`. The item is backed by `wal.growth_rate` (snapshot metric).

## What this item shows
- WAL bytes generated per second over time.
- Current write-ahead-log production rate.

## What to watch
- WAL spikes during DML or bulk load.
- Sustained WAL rate near archive or replication capacity.
- WAL rate increasing after release.

## Common fault causes
- Bulk writes.
- Full-page images after checkpoint.
- Index-heavy updates.
- Large transactions.

## Checklist
- Compare with Top SQL by WAL and SQL WAL Delta.
- Check archive/replication capacity.
- Review checkpoint timing for FPI-heavy periods.
