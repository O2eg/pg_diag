# PostgreSQL Settings

This instruction belongs to report item `overview.pg_settings`. The item is backed by `cluster.settings` (SQL query).

## What this item shows
- Current runtime settings visible through `pg_settings`
- Values, units, source, context, and restart-pending state where PostgreSQL exposes them.
- Configuration evidence for memory, WAL, autovacuum, planner, logging, connection, and extension behavior.

## What to watch
- Settings with `pending_restart=true`
- Settings sourced from unexpected files, ALTER SYSTEM, database, role, or session overrides.
- Values that do not match the approved baseline for this environment.
- Memory and parallelism settings that are unsafe for the configured connection count.

## Common fault causes
- Configuration changed but PostgreSQL was not restarted for postmaster-context settings.
- Role or database overrides hiding the cluster-level value.
- Package upgrade or restore copied an old configuration file.
- Manual ALTER SYSTEM changes made outside change control.

## Checklist
- Filter by changed settings first, then compare with baseline.
- Check `context` before deciding whether reload or restart is required.
- Review `sourcefile` and `sourceline` before editing configuration.
- Treat security-sensitive settings such as SSL, logging, authentication helpers, and search_path-related settings carefully.
