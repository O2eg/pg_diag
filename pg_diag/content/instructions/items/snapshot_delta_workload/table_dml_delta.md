# Table DML Delta

This instruction belongs to report item `snapshot_delta_workload.table_dml_delta`. The item is backed by `objects.table_dml_delta` (snapshot metric).

## What this item shows
- Insert, update, delete, HOT-update, total-DML delta, and total DML/s for table OIDs present at both endpoints.
- Current schema/table labels with stable `(datid, relid)` identity.
- Up to 200 lifetime-DML candidates per endpoint, reduced to 50 derived rows.

## What to watch
- One relation dominating writes, unexpected deletes/inserts, or updates greatly exceeding HOT updates.

## Automatic evaluation
- No severity is assigned because write volume and desired HOT ratio are schema/workload-specific.
- HOT updates are a subset of updates; compare their deltas rather than treating either counter as a percentage.

## Interval coverage
- A database-wide `stats_reset` change invalidates comparable rows even if counters regrew above their starting values.
- Single-table reset has no timestamp in these views. A decrease is detected, but a reset followed by growth above the start value remains a PostgreSQL observability limitation.
- OID identity survives renames; drop/recreate or bounded Top-200 churn appears as unmatched endpoints.

## Common fault causes
- Application hotspot, batch processing, retention purge, HOT-unfriendly indexes/fillfactor, or external statistics reset.

## Related report items
- [snapshot_charts_db.tables_top_dml_rate](#item-snapshot_charts_db.tables_top_dml_rate) — Inspect per-interval table write hotspots.
- [snapshot_delta_workload.table_maintenance_delta](#item-snapshot_delta_workload.table_maintenance_delta) — Check maintenance work following DML.
- [snapshot_delta_workload.sql_wal_delta](#item-snapshot_delta_workload.sql_wal_delta) — Relate table changes to WAL-producing SQL.

## Checklist
- Correlate hot relations with WAL, autovacuum, and statement deltas.
- Inspect update/index patterns before changing fillfactor or indexes.
- Treat this as a bounded candidate set, not a scan of every relation in large databases.
- Empty means no non-zero comparable candidate.
