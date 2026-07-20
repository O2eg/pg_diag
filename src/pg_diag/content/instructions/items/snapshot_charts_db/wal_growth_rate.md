# WAL Growth Rate

This instruction belongs to report item `snapshot_charts_db.wal_growth_rate`. The item is backed by `wal.growth_rate` (snapshot metric).

## What this item shows
- WAL bytes generated per second over time.
- Cluster-wide write-ahead-log production rate; it is not attributable to the connected database.

## What to watch
- WAL spikes during DML or bulk load.
- Sustained WAL rate near archive or replication capacity.
- WAL rate increasing after release.

## Common fault causes
- Bulk writes.
- Full-page images after checkpoint.
- Index-heavy updates.
- Large transactions.

## Automatic evaluation
- The source is cluster-wide `pg_stat_wal`; counter decreases after a stats reset become missing points.
- No fixed severity is assigned because archive and replication capacity define the safe rate.

## Related report items
- [sql_workload.top_sql_by_wal](#item-sql_workload.top_sql_by_wal) — Attribute cumulative WAL generation to statements.
- [snapshot_delta_workload.sql_wal_delta](#item-snapshot_delta_workload.sql_wal_delta) — Attribute WAL inside the capture window.
- [snapshot_delta_workload.wal_archiver_delta](#item-snapshot_delta_workload.wal_archiver_delta) — Check whether archiving keeps pace.

## Checklist
- Compare with Top SQL by WAL and SQL WAL Delta.
- Check archive/replication capacity.
- Review checkpoint timing for FPI-heavy periods.
