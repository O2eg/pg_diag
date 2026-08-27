# Group Roles Without Members

This instruction belongs to report item `users_roles.group_roles_without_members`. The item is backed by `roles.group_roles_without_members` (SQL query).

## What this item shows
- `NOLOGIN` roles that have no direct members.
- Evidence of remaining usage: the groups such a role belongs to, its own settings, database privileges, and default-privilege entries in the connected database.

## What to watch
- Empty groups that still carry privileges; they can be granted to a user later and silently reopen access.
- Empty groups with administrative attributes such as `create_role` or `bypass_rls`.
- Groups that exist only to own objects; they are legitimate and must not be removed.

## Common fault causes
- Access groups created for a project or team that has been dissolved.
- Role templates cloned from another cluster without the users that used them.
- Owner groups that were intentionally created empty.

## Automatic evaluation
- Every row carries `unknown` severity: the cluster does not record whether an empty group is still required.
- Object ownership in the connected database is not part of this check; use the ownership item before removal.
- The list covers the first 1,000 empty groups; `result_truncated` marks partial coverage.

## Related report items
- [users_roles.object_ownership_by_role](#item-users_roles.object_ownership_by_role) — Check whether an empty group owns objects before dropping it.
- [users_roles.object_privileges_by_grantee](#item-users_roles.object_privileges_by_grantee) — Check whether an empty group still holds object privileges.
- [users_roles.role_membership](#item-users_roles.role_membership) — Review the membership edges that remain.

## Checklist
- Confirm the purpose of each empty group with its owner.
- Revoke privileges from groups that are kept only for historical reasons.
- Drop groups that own nothing and are referenced nowhere.
