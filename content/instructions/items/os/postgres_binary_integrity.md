# PostgreSQL Binary Integrity

This item checks PostgreSQL executable ownership and write permissions.

## What this item shows
- Visible PostgreSQL command paths such as `postgres`, `psql`, and backup tools.
- Group/world writable binaries.
- Unexpected binary owners.

## Checklist
- Keep binaries owned by root or postgres.
- Remove group/world write permissions.
- Reinstall packages if executable integrity is uncertain.
