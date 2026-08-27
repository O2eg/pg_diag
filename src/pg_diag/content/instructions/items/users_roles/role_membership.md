# Role Membership

This instruction belongs to report item `users_roles.role_membership`. The item is backed by `roles.membership` (SQL query).

## What this item shows
- Every direct `GRANT role TO member` edge from `pg_auth_members`: the member, the granted role, the grantor, and `admin_option`.
- Whether the granted role can log in, is a superuser, or is a predefined `pg_*` role.
- `member_inherits_by_default` reflects the member's `INHERIT` attribute; on PostgreSQL 16 and newer `inherit_option` and `set_option` show the per-membership options, on older versions those columns are unsupported.

## What to watch
- Login roles granted directly into superuser or owner roles.
- Memberships with `admin_option` held by application roles.
- Memberships whose grantor is an application account rather than an administrator.
- `set_option = false` together with `inherit_option = false`, which makes a membership ineffective.

## Common fault causes
- `GRANT role TO user` executed ad hoc during incidents.
- Migration tooling connected as a superuser that granted itself into application roles.
- Access models that use direct grants to users instead of groups.

## Automatic evaluation
- This item is an inventory and assigns no risk to individual memberships.
- The list covers the first 5,000 memberships; `result_truncated` marks partial coverage and sets the item severity to `unknown`.

## Related report items
- [users_roles.effective_role_membership](#item-users_roles.effective_role_membership) — Follow transitive membership paths and their reach.
- [users_roles.admin_option_holders](#item-users_roles.admin_option_holders) — Review who can change memberships.
- [cluster_inventory.predefined_admin_role_membership](#item-cluster_inventory.predefined_admin_role_membership) — Review memberships in predefined administrative roles.

## Checklist
- Verify every membership against the documented access model.
- Revoke `ADMIN OPTION` from non-administrative roles.
- Prefer group roles over direct user memberships in owner roles.
