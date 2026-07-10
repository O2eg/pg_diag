# PostgreSQL Config File Permissions

This instruction belongs to `os.postgres_config_file_permissions`, backed by local Python source `security.postgres_config_file_permissions`.

## What this item shows
- `postgresql.conf`, `pg_ident.conf`, `postgresql.auto.conf`, and `conf.d` files when visible locally.
- File owner, group, mode, and expected mode.

## What to watch
- World-readable/writable files, group-writable files, or an active `config_file` that cannot be inspected.

## Automatic evaluation
- World read/write exposure is `high`; other disallowed permission bits or unavailable path evidence are `medium`.
- `empty` means no finding among discovered files, not that every possible include path was scanned.

## Common fault causes
- Package defaults changed manually, copied configuration, permissive umask, or a configuration-management ownership error.

## Checklist
- Keep configuration files at `0600` or `0640`.
- Restrict write access to PostgreSQL administrators.
- Check include directories used by the active cluster.
