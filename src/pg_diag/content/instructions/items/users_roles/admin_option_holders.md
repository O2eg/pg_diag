# Role Administration Rights

This instruction belongs to report item `users_roles.admin_option_holders`. The item is backed by `roles.admin_option_holders` (SQL query).

## What this item shows
- Roles holding `ADMIN OPTION` on another role, with the administered role and the grantor.
- Roles with the `CREATEROLE` attribute; on PostgreSQL 15 and older this grants control over every non-superuser role, on 16 and newer only over roles the holder created.

## What to watch
- Application or service accounts with `ADMIN OPTION` or `CREATEROLE`; they can grant themselves or others into privileged groups.
- `CREATEROLE` on PostgreSQL 15 and older, which can also alter passwords of other roles.
- Administration rights granted by non-administrative grantors.

## Common fault causes
- `GRANT role TO user WITH ADMIN OPTION` copied from documentation examples.
- `CREATEROLE` given to deployment tooling for convenience.
- Ownership of role management never assigned to a dedicated administrator role.

## Automatic evaluation
- `medium`: a non-superuser holds `ADMIN OPTION` or `CREATEROLE`.
- `ok`: superusers, which already administer every role.
- The list covers 3,000 admin-option memberships and 1,000 `CREATEROLE` roles; `result_truncated` marks partial coverage.

## Related report items
- [users_roles.role_membership](#item-users_roles.role_membership) — Review the memberships that administration rights can change.
- [cluster_inventory.privileged_roles](#item-cluster_inventory.privileged_roles) — Review other cluster-level attributes of the same roles.
- [users_roles.effective_role_membership](#item-users_roles.effective_role_membership) — Check which privileged roles an administrator can reach.

## Checklist
- Limit `ADMIN OPTION` and `CREATEROLE` to role-management accounts.
- Use PostgreSQL 16 semantics or explicit `ADMIN OPTION` grants to scope role administration.
- Audit role changes made by the listed roles.
