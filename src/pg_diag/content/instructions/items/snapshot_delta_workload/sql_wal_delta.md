# SQL WAL Delta

This instruction belongs to report item `snapshot_delta_workload.sql_wal_delta`. The item is backed by `statements.wal_delta` (snapshot metric).

## What this item shows
- WAL byte, record, and full-page-image deltas for statement entries present at both endpoints.
- WAL bytes per second and full `(dbid, userid, queryid, toplevel)` identity.
- Up to 50 candidates selected by cumulative WAL bytes before rows enter collector memory.

## What to watch
- High WAL bytes per second, full-page images after checkpoints, and WAL-heavy SQL aligned with archive or replication pressure.

## Automatic evaluation
- No severity is assigned because expected WAL volume and available retention/replication capacity are deployment-specific.
- Generated WAL is not itself proof of archive failure or replication lag.

## Interval coverage
- Global reset epoch is checked on all supported versions and per-entry epoch on PostgreSQL 17+.
- Counter decreases and epoch changes are omitted as invalid; bounded-selection churn remains informational.
- Rows with hidden query ID are excluded rather than collapsed.

## Common fault causes
- Bulk writes, indexed-column updates, full-page images, large transactions, reset, or entry eviction.

## Related report items
- [snapshot_delta_workload.sql_time_delta](#item-snapshot_delta_workload.sql_time_delta) — Relate WAL generation to statement execution.
- [snapshot_charts_db.wal_growth_rate](#item-snapshot_charts_db.wal_growth_rate) — Compare statement WAL with the cluster-wide rate.
- [snapshot_delta_workload.checkpointer_delta](#item-snapshot_delta_workload.checkpointer_delta) — Check checkpoint activity during WAL generation.

## Checklist
- Correlate with WAL growth, checkpoints, archiver, and replication items.
- Normalize WAL by calls/rows using the matching SQL identity where useful.
- Review schema/index write amplification before changing durability policy.
- Empty means no non-zero comparable candidate; unsupported means pg_stat_statements evidence is unavailable.
