# Role Inventory

This instruction belongs to report item `users_roles.roles_inventory`. The item is backed by `roles.inventory` (SQL query).

## What this item shows
- Every role visible in `pg_roles`, including predefined `pg_*` roles marked by `is_predefined`.
- Role attributes: `can_login`, `superuser`, `inherit`, `create_role`, `create_db`, `replication`, `bypass_rls`, `connection_limit`, and `valid_until`.
- Direct group memberships in `member_of` with `member_of_count`, the number of direct members in `direct_member_count`, the number of `ALTER ROLE SET` entries in `setting_count`, and the role comment.
- `valid_until_expired` is true when `valid_until` lies in the past; a role without expiry shows `valid_until` as empty.

## What to watch
- Login roles that are also superusers, `create_role`, or `bypass_rls`; application accounts normally need none of these attributes.
- Login roles without `connection_limit` (`-1`) that serve unpooled applications.
- Roles whose `member_of` includes owner or administrative groups without a documented reason.
- Roles that own nothing, belong to nothing, and have no settings; they may be leftovers.

## Common fault causes
- Accounts created for migrations, support, or troubleshooting and never removed.
- Application roles created as superusers to bypass permission errors.
- Group hierarchy that drifted from the documented access model after ad-hoc `GRANT role` statements.

## Automatic evaluation
- This item is an inventory and assigns no risk to individual roles.
- The inventory covers the first 5,000 roles by name and the first 20,000 direct memberships; `role_sample_truncated` and `membership_sample_truncated` mark partial coverage and set the item severity to `unknown`.

## Related report items
- [cluster_inventory.privileged_roles](#item-cluster_inventory.privileged_roles) — Review the subset of roles with cluster-level attributes.
- [users_roles.role_membership](#item-users_roles.role_membership) — Inspect each membership edge with its ADMIN, INHERIT, and SET options.
- [users_roles.role_database_settings](#item-users_roles.role_database_settings) — See the per-role settings counted in `setting_count`.
- [users_roles.password_validity](#item-users_roles.password_validity) — Review password expiry for login roles.

## Checklist
- Compare the role list with the approved role baseline and remove unknown roles.
- Confirm that every superuser, `create_role`, and `bypass_rls` role is an administrative account.
- Record the purpose of every group role and verify its members.
