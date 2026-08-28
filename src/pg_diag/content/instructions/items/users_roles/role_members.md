# Role Members

This instruction belongs to report item `users_roles.role_members`. The item is backed by `roles.group_members` (SQL query).

## What this item shows
- Every role that has at least one direct member, including predefined `pg_*` roles such as `pg_monitor`.
- `login_members` lists the direct members that can log in; `nologin_members` lists the direct members that are group roles.
- PostgreSQL does not record whether a role was created with `CREATE USER` or `CREATE ROLE`; the only durable difference is the `LOGIN` attribute, which this item uses to split the member lists into users and groups.
- `direct_member_count` is the exact number of direct members even when a member list is cut at 500 characters.

## What to watch
- Login roles granted directly into superuser or owner roles.
- Predefined administrative roles with unexpected members.
- Group roles nested inside other group roles, which hide the effective reach of a grant.
- Roles that mix login and group members, which usually signals an inconsistent access model.

## Common fault causes
- `GRANT role TO user` executed ad hoc during incidents.
- Provisioning tooling that grants every new user into a catch-all group.
- Access models that grant privileges to individual users instead of group roles.

## Automatic evaluation
- This item is an inventory and assigns no risk to individual roles.
- The item covers the first 20,000 memberships and the first 5,000 roles with members; `membership_sample_truncated` and `role_sample_truncated` mark partial coverage and set the item severity to `unknown`.

## Related report items
- [users_roles.role_membership](#item-users_roles.role_membership) — Inspect each membership edge with grantor and ADMIN, INHERIT, and SET options.
- [users_roles.effective_role_membership](#item-users_roles.effective_role_membership) — Follow transitive membership paths and their reach.
- [users_roles.group_roles_without_members](#item-users_roles.group_roles_without_members) — Review group roles that have no members at all.
- [users_roles.roles_inventory](#item-users_roles.roles_inventory) — See every role with its attributes and its own group memberships.

## Checklist
- Verify each member list against the documented access model.
- Prefer granting privileges to group roles and adding users as members over direct user grants.
- Review the members of predefined administrative roles.
