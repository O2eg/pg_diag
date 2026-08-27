# Published Tables Without Replica Identity

This instruction belongs to report item `replication.publication_tables_replica_identity`. The item is backed by `replication.publication_replica_identity` (SQL query).

## What this item shows
- Tables included in publications of the connected database - explicitly, through `FOR TABLES IN SCHEMA` (PostgreSQL 15 and newer), or through `FOR ALL TABLES` - whose replica identity cannot support replicated `UPDATE` and `DELETE`: `REPLICA IDENTITY NOTHING`, or the default identity without a primary key.
- Unlogged tables inside publications and tables with `REPLICA IDENTITY FULL`.
- For each finding: publication, publish mode, relation kind, replica identity, primary key presence, replica identity index, persistence, and whether the publication publishes updates and deletes.

## What to watch
- `high` rows: the next `UPDATE` or `DELETE` on the publisher fails with "cannot update table because it does not have a replica identity".
- Unlogged tables: their changes never reach subscribers although the publication lists them.
- `REPLICA IDENTITY FULL` on large or wide tables; every change ships all columns and the subscriber must scan for matches.
- Partitioned parents: the identity check applies to each leaf partition.

## Common fault causes
- `FOR ALL TABLES` publications that silently include new tables created without a primary key.
- Primary keys dropped during migrations while the table stays published.
- Staging tables created as unlogged inside published schemas.

## Automatic evaluation
- `high`: a plain table without a usable replica identity is in a publication that publishes updates or deletes.
- `medium`: an unlogged table is published.
- `unknown`: `REPLICA IDENTITY FULL`, a partitioned parent without identity, or an insert-only publication with a table that lacks identity.
- Stored tables are sampled by descending `relpages` (10,000), empty tables by name (10,000), publications (200), explicit memberships (10,000), schema memberships (1,000), and expanded memberships (20,000); coverage flags mark partial results and add a `[coverage]` row.

## Related report items
- [users_roles.publication_ownership](#item-users_roles.publication_ownership) — Review the publications and their published operations.
- [indexes.tables_without_pk_or_unique](#item-indexes.tables_without_pk_or_unique) — Find tables without a primary key across the database.
- [replication.subscription_table_sync](#item-replication.subscription_table_sync) — Check the subscriber-side state of the same tables.

## Checklist
- Add a primary key or `REPLICA IDENTITY USING INDEX` to every published table.
- Exclude staging and unlogged tables from publications.
- Review `REPLICA IDENTITY FULL` tables for WAL and subscriber cost.
