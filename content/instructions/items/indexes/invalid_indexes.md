# Invalid Indexes

This instruction belongs to report item `indexes.invalid_indexes`. The item is backed by `indexes.invalid_indexes` (SQL query).

## What this item shows
- Indexes marked invalid or not ready/valid for normal planner use.
- Index definitions that may result from failed concurrent builds or interrupted DDL.
- Objects needing index rebuild/drop review.

## What to watch
- Any invalid index on production tables.
- Invalid unique or constraint-backed indexes.
- Repeated invalid indexes after migrations.

## Common fault causes
- Failed CREATE INDEX CONCURRENTLY.
- Interrupted REINDEX.
- Crash during DDL.
- Manual catalog state after failed migration.

## Automatic evaluation
- `high`: the invalid/not-ready/not-live index backs a constraint.
- `medium`: any other invalid index requires failed-DDL or rebuild review.
- The query limits candidates by catalog pages before calculating exact size and does not issue DDL.

## Checklist
- Check whether a valid equivalent index exists.
- Rebuild or drop invalid indexes in a maintenance-safe way.
- Review migration logs for root cause.
