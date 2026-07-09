# PGDATA Permissions

This item reports PostgreSQL data directory permissions broader than expected.

## What this item shows
- `data_directory` path reported by PostgreSQL.
- Directory mode visible to the local collector.
- Risk level for group or world access.

## Checklist
- Keep PGDATA permissions at `0700` or tightly controlled `0750`.
- Limit access to the PostgreSQL OS account and trusted administrators.
- Re-check permissions after restore, rsync, or package operations.
