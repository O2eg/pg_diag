# Tables Without PK Or Unique Index

This instruction belongs to report item `indexes.tables_without_pk_or_unique`. The item is backed by `indexes.tables_without_pk_or_unique` (SQL query).

## What this item shows
- User tables without primary key or any valid unique index.
- Tables lacking stable row identity.
- Potential replication, deduplication, and application consistency risks.

## What to watch
- Tables intended for OLTP without a key.
- Tables planned for logical replication.
- Large tables where duplicate rows would be hard to repair.

## Common fault causes
- Schema shortcut.
- Staging table promoted to production.
- Legacy table never normalized.

## Automatic evaluation
- `medium`: a non-partition child with at least 100,000 estimated rows lacks a valid non-partial primary or unique index.
- `unknown`: smaller or empty tables require lifecycle context.
- A nullable unique key may still be unsuitable as logical-replication identity; validate the actual constraint semantics.

## Checklist
- Confirm whether table is transient/staging.
- Add a primary key or appropriate unique constraint for durable tables.
- Resolve duplicates before adding uniqueness.
