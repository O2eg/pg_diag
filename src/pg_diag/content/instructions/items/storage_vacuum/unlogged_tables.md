# Unlogged Relations

This instruction belongs to report item `storage_vacuum.unlogged_tables`. The item is backed by `storage.unlogged_tables` (SQL query).

## What this item shows
- User tables and sequences created with UNLOGGED persistence, largest first.
- `total_bytes` includes the relation with its indexes and TOAST data; indexes of an unlogged table are unlogged too.
- Unlogged relations skip WAL: they are emptied during crash recovery and do not exist on physical standbys.

## What to watch
- Large unlogged tables holding data that is expensive or impossible to rebuild.
- Unlogged tables read by application code that assumes the data survives a failover.
- Unlogged sequences (PostgreSQL 15+) backing identifiers that must not repeat.

## Common fault causes
- Staging or ETL tables promoted into permanent use without ALTER TABLE ... SET LOGGED.
- Performance tuning that traded durability for write speed and was forgotten.

## Automatic evaluation
- Every unlogged relation reports `medium` for review; unlogged persistence is legitimate for reconstructible data.
- The list covers the 500 largest unlogged relations and marks truncation.

## Related report items
- [storage_vacuum.table_size_detailed](#item-storage_vacuum.table_size_detailed) — Full storage breakdown of the largest tables.
- [replication.publication_tables_replica_identity](#item-replication.publication_tables_replica_identity) — Logical replication safety of published tables; unlogged tables cannot be replicated at all.

## Checklist
- Confirm every unlogged relation holds only data that can be rebuilt from another source.
- Convert the rest with ALTER TABLE ... SET LOGGED and plan for the WAL volume that rewrite generates.
