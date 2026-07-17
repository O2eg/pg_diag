# Database Volume

This instruction belongs to report item `overview.database_volume`. The item is backed by `database.database_volume` (trusted Python source).

## What this item shows

- One row for every database listed by `pg_database`, ordered by database size from largest to smallest.
- The on-disk database size returned by `pg_database_size` and logical counts of user schemas, relations, routines, triggers, constraints, types, collations, conversions, extended statistics, policies, rules, extensions, publications, subscriptions, large objects, and foreign-data objects.
- Separate `partitions` and `index_partitions` columns for physical partition children that are excluded from the logical `tables` and `indexes` counts.
- A row-local collection status when a database does not accept connections, the diagnostic role lacks `CONNECT`, or a catalog query fails.
- A typed `Timeout` cell status for `database_size_bytes` when a size calculation exceeds 10 seconds; the numeric raw cell remains null.

## What to watch

- Rapid size growth, unexpectedly large databases, or object counts that approach operational tooling limits.
- Large numbers of partitioned relations, indexes, functions, triggers, or policies that can increase planning, maintenance, backup, and schema-management cost.
- Size timeouts, connection failures, or entity-count failures that leave a database only partially inventoried.
- Databases that no longer serve a workload but still retain substantial storage or schema objects.

## Automatic evaluation

This item is informational. It preserves partial rows and collection errors but does not infer severity from database size or object counts because acceptable values depend on workload, storage, retention, and maintenance design.

## Common fault causes

- Large tables, indexes, TOAST data, temporary spill files retained during collection, or accumulated bloat.
- Excessive partition creation, obsolete indexes, abandoned schemas, or extension-owned objects.
- Missing `CONNECT` privilege, `datallowconn = false`, a database being dropped or renamed during collection, or connection-slot pressure.
- Slow storage or catalog contention causing `pg_database_size` to exceed its 10-second limit.

User-object counts exclude `pg_catalog`, `information_schema`, temporary schemas, and TOAST schemas. Database size includes the complete database storage reported by PostgreSQL, including system catalogs and TOAST data.
`tables` counts non-partition relations and top-level partitioned tables. `partitioned_tables` is the top-level parent-table subset; `partitions` is the physical child count, including leaf and nested partitioned relations. The three index columns follow the same rule. Triggers, constraints, row-security policies, and rules attached to child partitions are excluded from their logical totals.

## Related report items
- [storage_vacuum.table_size_detailed](#item-storage_vacuum.table_size_detailed) — Attribute database volume to the largest tables and indexes.
- [overview.database_stats](#item-overview.database_stats) — Compare size with cumulative database workload.

## Checklist

1. Start with the largest databases and compare their sizes with available storage and expected retention.
2. Compare table and index counts; investigate databases whose index inventory is unexpectedly large for their table count.
3. Review databases with a non-`ok` collection status and grant only the minimum access required for diagnostics.
4. Re-run the report outside peak load before acting on an isolated size timeout.
