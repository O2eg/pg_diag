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

## Related report items
- [overview.pg_settings](#item-overview.pg_settings) — Compare pending values with active PostgreSQL settings.
- [overview.server_version](#item-overview.server_version) — Check version-specific setting and restart behavior.

## Checklist
- Schedule restart for intended changes.
- Rollback unintended pending changes.
- Verify active value after restart.
