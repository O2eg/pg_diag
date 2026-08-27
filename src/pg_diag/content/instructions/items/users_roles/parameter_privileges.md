# Parameter Privileges

This instruction belongs to report item `users_roles.parameter_privileges`. The item is backed by `roles.parameter_privileges` (SQL query).

## What this item shows
- `SET` and `ALTER SYSTEM` privileges granted on server parameters through `GRANT ... ON PARAMETER`, available on PostgreSQL 15 and newer.
- The grantee, its kind, whether the grantee is a superuser, and the grantor.
- On PostgreSQL 14 and older the item is reported as unsupported.

## What to watch
- `ALTER SYSTEM` granted to non-superusers; they can change persistent server configuration.
- `SET` on parameters such as `log_statement`, `session_replication_role`, or `zero_damaged_pages` that weaken auditing or safety.
- Parameter privileges granted to `PUBLIC`.

## Common fault causes
- Delegated configuration management set up with broader parameter grants than needed.
- Application roles granted `SET` to work around superuser-only parameters.

## Automatic evaluation
- `medium`: a non-superuser holds `ALTER SYSTEM` on a parameter.
- `unknown`: all other parameter grants; whether they are acceptable depends on the configuration baseline.
- The list covers 1,000 parameters and 3,000 ACL entries; coverage flags mark partial results and add a `[coverage]` row.

## Related report items
- [overview.pg_settings](#item-overview.pg_settings) — Check the current values of the granted parameters.
- [cluster_inventory.pending_restart_settings](#item-cluster_inventory.pending_restart_settings) — Detect configuration changes waiting for a restart.

## Checklist
- Keep `ALTER SYSTEM` grants limited to configuration-management roles.
- Review each `SET` grant against the security and logging policy.
