# PostgreSQL Environment Secret Leaks

This item checks readable process environments for PostgreSQL credentials.

## What this item shows
- Process id and command line for environments that appear to contain PostgreSQL secrets.
- Secret values are not printed.

## Checklist
- Avoid long-lived `PGPASSWORD` environment variables.
- Prefer protected service files, peer auth, or secret managers.
- Restart affected processes after rotating exposed credentials.
