# PostgreSQL Config File Permissions

This item checks local PostgreSQL configuration file permissions.

## What this item shows
- `postgresql.conf`, `pg_ident.conf`, `postgresql.auto.conf`, and `conf.d` files when visible locally.
- File owner, group, mode, and expected mode.

## Checklist
- Keep configuration files at `0600` or `0640`.
- Restrict write access to PostgreSQL administrators.
- Check include directories used by the active cluster.
