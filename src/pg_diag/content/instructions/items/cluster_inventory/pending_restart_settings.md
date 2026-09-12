# Settings Pending Restart

This instruction belongs to report item `cluster_inventory.pending_restart_settings`. The item is backed by `cluster.pending_restart_settings` (SQL query).

## What this item shows
- Settings whose current configured value requires PostgreSQL restart to take effect.
- Postmaster-context configuration changes waiting for restart.
- Configuration drift between file/ALTER SYSTEM value and active runtime.

## What to watch
- Any security, memory, WAL, or preload setting pending restart.
- shared_preload_libraries changes not active.
- Restart-pending settings after maintenance.

## Common fault causes
- Reload used when restart was required.
- ALTER SYSTEM applied without maintenance window.
- Package or config management changed files.

## Automatic evaluation
- This is operational evidence, not an automatic severity: a pending restart may be planned.
- Values are server-scoped and include source file/line when visible.
- `pending_restart_kind = auto_computed_artifact` marks a setting whose file value equals `boot_val` (the "auto" sentinel such as `-1`) **and** whose running value the server itself computed at startup (`pg_settings.source = override`; `io_max_concurrency` on PostgreSQL 18 is the common case). Every reload compares the file value with the computed one and raises the flag again; a restart recomputes the same value and does not clear it, so this row needs no action. A file value that merely returns a setting to its default while the running value came from the command line or an earlier file is a real `configuration_change` and still needs the restart. The diagnostic graph scores only `configuration_change` rows.

## Related report items
- [overview.pg_settings](#item-overview.pg_settings) — Compare pending values with active PostgreSQL settings.
- [overview.server_version](#item-overview.server_version) — Check version-specific setting and restart behavior.

## Checklist
- Schedule restart for intended changes.
- Rollback unintended pending changes.
- Verify active value after restart.
