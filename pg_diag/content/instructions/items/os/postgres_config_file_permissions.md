# PostgreSQL Config File Permissions

This instruction belongs to report item `os.postgres_config_file_permissions`.
It is backed by local Python source `security.postgres_config_file_permissions`.

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

## Related report items
- [cluster_inventory.pg_hba_file_permissions](#item-cluster_inventory.pg_hba_file_permissions) — Cross-check HBA-specific file permissions.
- [cluster_inventory.pgdata_permissions](#item-cluster_inventory.pgdata_permissions) — Review protection of the containing data directory.
- [overview.pg_settings](#item-overview.pg_settings) — Identify active configuration file locations and settings.

## Checklist
- Keep configuration files at `0600` or `0640`.
- Restrict write access to PostgreSQL administrators.
- Check include directories used by the active cluster.
