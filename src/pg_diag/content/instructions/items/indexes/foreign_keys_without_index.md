# Foreign Keys Without Supporting Index

This instruction belongs to report item `indexes.foreign_keys_without_index`. The item is backed by `indexes.foreign_keys_without_index` (SQL query).

## What this item shows
- Foreign keys whose referencing columns are not supported by a left-prefix valid index.
- Tables where parent deletes/updates may scan referencing rows.
- FK-related lock and performance risk candidates.

## What to watch
- High-write parent tables with unindexed referencing FKs.
- Large child tables without supporting indexes.
- Multiple missing FK indexes after schema migration.

## Common fault causes
- ORM did not create FK indexes.
- Manual schema change omitted index.
- Index dropped as unused without FK review.

## Automatic evaluation
- `medium`: the referencing table estimate is at least 100,000 rows and no valid full non-partial left-prefix index exists.
- `unknown`: the same structural gap exists on a smaller table; parent UPDATE/DELETE frequency determines impact.
- `suggested_index` is a starting definition, not executable advice for partitioned tables or a substitute for workload review.

## Related report items
- [snapshot_delta_workload.table_scan_delta](#item-snapshot_delta_workload.table_scan_delta) — Check whether FK checks contribute to table scans.
- [activity_locks.lock_waits](#item-activity_locks.lock_waits) — Investigate locking during parent-row updates or deletes.
- [indexes.tables_without_pk_or_unique](#item-indexes.tables_without_pk_or_unique) — Review related key-design gaps.

## Checklist
- Prioritize FKs where parent rows are updated/deleted.
- Create supporting index concurrently where needed.
- Balance read/write benefit against added index maintenance.
