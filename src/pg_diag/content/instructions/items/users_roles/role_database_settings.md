# Role And Database Settings

This instruction belongs to report item `users_roles.role_database_settings`. The item is backed by `roles.database_settings` (SQL query).

## What this item shows
- Every parameter set with `ALTER ROLE ... SET`, `ALTER ROLE ... IN DATABASE ... SET`, or `ALTER DATABASE ... SET`, read from `pg_db_role_setting`.
- `scope` identifies which of the three forms applies; `[all roles]` and `[all databases]` mark the unrestricted side.
- `applies_to_current_database` shows whether the entry affects sessions in the connected database; `setting_context` and `setting_category` come from `pg_settings`.
- Values of parameters whose name looks like a secret are redacted.

## What to watch
- `search_path`, `statement_timeout`, `lock_timeout`, `work_mem`, and `log_*` overrides that differ from the server configuration and explain unexpected session behaviour.
- Overrides on superuser or maintenance roles that disable timeouts or logging.
- Settings on roles or databases that no longer exist in the access model.

## Common fault causes
- Per-role tuning applied during an incident and never reverted.
- Application roles with `search_path` pointing at schemas that changed later.
- Database-level defaults that mask server-level configuration changes.

## Automatic evaluation
- This item is an inventory and assigns no risk to individual settings.
- The list covers the first 5,000 setting entries; `result_truncated` marks partial coverage and sets the item severity to `unknown`.

## Related report items
- [overview.pg_settings](#item-overview.pg_settings) — Compare with the effective server-level configuration.
- [users_roles.roles_inventory](#item-users_roles.roles_inventory) — See the per-role setting count in the role inventory.

## Checklist
- Document every per-role and per-database override.
- Remove overrides that were introduced for troubleshooting.
- Keep timeouts and logging overrides consistent with the security policy.
