# PostgreSQL Settings

This instruction belongs to report item `overview.pg_settings`. The item is backed by `cluster.settings` (SQL query).

## What this item shows
- Current runtime settings visible through `pg_settings`.
- Values, units, source, context, and restart-pending state where PostgreSQL exposes them.
- Source file/line, boot value, and reset value when visible to the collector role.
- Configuration evidence for memory, WAL, autovacuum, planner, logging, connection, and extension behavior.

## What to watch
- Settings with `pending_restart=true`
- Settings sourced from unexpected files, ALTER SYSTEM, database, role, or session overrides.
- Values that do not match the approved baseline for this environment.
- Memory and parallelism settings that are unsafe for the configured connection count.

## Automatic evaluation
- `medium` is assigned when at least one setting has `pending_restart=true`.
- `medium` is also assigned when `work_mem` remains at the PostgreSQL boot default.
- Default `work_mem` is a review signal, not proof that it is too small. Global increases multiply across concurrent operations and sessions.
- The collector temporarily guards its own `lock_timeout` and `statement_timeout`; displayed values use the pre-collector reset value for those settings.

## Common fault causes
- Configuration changed but PostgreSQL was not restarted for postmaster-context settings.
- Role or database overrides hiding the cluster-level value.
- Package upgrade or restore copied an old configuration file.
- Manual ALTER SYSTEM changes made outside change control.

## Related report items
- [cluster_inventory.pending_restart_settings](#item-cluster_inventory.pending_restart_settings) — Find settings whose requested values are not active yet.
- [overview.stat_reset_times](#item-overview.stat_reset_times) — Separate configuration changes from statistics-reset effects.

## Checklist
- Filter by changed settings first, then compare with baseline.
- Check `context` before deciding whether reload or restart is required.
- Review `sourcefile` and `sourceline` before editing configuration.
- Treat security-sensitive settings such as SSL, logging, authentication helpers, and search_path-related settings carefully.
- Use spill evidence, concurrency, query plans, and total memory budget before changing `work_mem`.
