# Effective Role Membership

This instruction belongs to report item `users_roles.effective_role_membership`. The item is backed by `roles.effective_membership` (SQL query).

## What this item shows
- The transitive closure of role membership: for each member, every role reachable through one or more `GRANT role` edges with `depth` and the full `path`.
- `inherits_privileges` shows whether object privileges flow automatically along the whole path; `can_set_role` shows whether `SET ROLE` to the reached role is allowed (always true before PostgreSQL 16).
- Whether the reached role is a superuser or a predefined `pg_*` role, and its strong attributes in `inherited_role_attributes` (`CREATEROLE`, `CREATEDB`, `REPLICATION`, `BYPASSRLS`); role attributes are never inherited but become available after `SET ROLE`.

## What to watch
- Non-superuser roles that reach a superuser role; with `can_set_role` they are effectively superusers.
- Long paths that make privilege review hard to reason about.
- Login roles that reach `pg_read_all_data`, `pg_write_all_data`, `pg_execute_server_program`, or similar roles indirectly.

## Common fault causes
- Group roles granted into other groups without reviewing what the target group already contains.
- A bootstrap superuser granted to a "dba" group that later receives ordinary members.
- Role hierarchies copied from another environment.

## Automatic evaluation
- `high`: a non-superuser reaches a superuser role and can `SET ROLE` to it.
- `medium`: a non-superuser can `SET ROLE` to a role with `CREATEROLE`, `CREATEDB`, `REPLICATION`, or `BYPASSRLS`, or reaches a predefined administrative role with inheritance or `SET ROLE`.
- `ok`: all other paths.
- Traversal is bounded to 3,000 rows and a depth of 32; `membership_truncated` marks partial coverage and adds a `[coverage]` row.

## Related report items
- [users_roles.role_membership](#item-users_roles.role_membership) — Inspect the individual edges that form each path.
- [cluster_inventory.privileged_login_roles](#item-cluster_inventory.privileged_login_roles) — Review the superuser login roles reached through membership.
- [cluster_inventory.predefined_admin_role_membership](#item-cluster_inventory.predefined_admin_role_membership) — Review predefined administrative role inheritance in detail.

## Checklist
- Remove membership paths that turn application roles into superusers.
- Flatten deep hierarchies where possible.
- Re-check paths after every `GRANT role` change in production.
