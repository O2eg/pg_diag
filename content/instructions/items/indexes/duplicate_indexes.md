# Duplicate Indexes

This instruction belongs to report item `indexes.duplicate_indexes`. The item is backed by `indexes.duplicate_indexes` (SQL query).

## What this item shows
- Indexes with identical key/operator/collation/predicate/expression fingerprints.
- True duplicate index candidates.
- Duplicate maintenance and storage overhead.

## What to watch
- Duplicate unique/constraint-related structures.
- Large duplicate indexes.
- Duplicates created by repeated migrations.

## Common fault causes
- Migration rerun.
- Manual CREATE INDEX duplicated existing index.
- Constraint/index naming confusion.

## Checklist
- Confirm dependencies before drop.
- Keep one valid index.
- Remove duplicates with production-safe DDL.
