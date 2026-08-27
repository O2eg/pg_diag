# Default Privileges

This instruction belongs to report item `users_roles.default_privileges`. The item is backed by `roles.default_privileges` (SQL query).

## What this item shows
- Every `ALTER DEFAULT PRIVILEGES` entry in the connected database: the defining role, the schema or `[all schemas]`, the object type, the grantee, `grantee_kind`, the privilege, and `is_grantable`.
- Entries granting to the defining role itself are omitted.

## What to watch
- Default privileges that grant to `PUBLIC` or to login roles.
- Default privileges defined for the wrong role: they apply only to objects created by the defining role, so objects created by another owner receive nothing.
- Missing default privileges for owner roles, which explains why new tables are unreadable by application groups.

## Common fault causes
- Default privileges configured for a superuser while migrations run as the owner role.
- `WITH GRANT OPTION` copied from examples.
- Schema-specific defaults that were not updated after a schema was renamed.

## Automatic evaluation
- This item is an inventory and assigns no risk to individual entries.
- The list covers 1,000 default ACL entries and 3,000 expanded rows; coverage flags mark partial results and add a `[coverage]` row.

## Related report items
- [object_workload.default_privileges_public_grants](#item-object_workload.default_privileges_public_grants) — Review the subset granted to PUBLIC or with grant option.
- [users_roles.object_privileges_by_grantee](#item-users_roles.object_privileges_by_grantee) — See the privileges that these defaults produced on existing objects.

## Checklist
- Define default privileges for the owner role that actually creates objects.
- Grant defaults to group roles rather than users or `PUBLIC`.
