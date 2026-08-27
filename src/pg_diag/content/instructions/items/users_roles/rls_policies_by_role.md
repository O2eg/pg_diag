# Row Level Security Policies By Role

This instruction belongs to report item `users_roles.rls_policies_by_role`. The item is backed by `roles.rls_policies_by_role` (SQL query).

## What this item shows
- Every row-level security policy in the connected database with the table, its owner, whether RLS is enabled and forced, the command, the permissive or restrictive type, and the roles the policy applies to (`PUBLIC` when unrestricted).
- `has_using` and `has_with_check` show which expressions the policy defines.

## What to watch
- Tables with policies but `rls_enabled = false`; the policies are inactive.
- Owners bypassing policies because `rls_forced = false`.
- Policies that apply only to `PUBLIC` while the application connects through specific roles, or policies restricted to roles that no longer exist.
- Permissive policies without a `WITH CHECK` expression on tables that receive writes.

## Common fault causes
- RLS enabled on a table but never forced for the owner used by the application.
- Policies written for a role that was replaced by a group.
- `BYPASSRLS` granted to application roles, which silently disables the policies.

## Automatic evaluation
- This item is an inventory and assigns no risk to individual policies.
- The list covers 3,000 policies; `result_truncated` marks partial coverage.

## Related report items
- [object_workload.rls_configuration](#item-object_workload.rls_configuration) — Review inactive, incomplete, or unforced policies flagged as risks.
- [object_workload.rls_table_privilege_mismatch](#item-object_workload.rls_table_privilege_mismatch) — Check table privileges that undermine RLS.
- [users_roles.roles_inventory](#item-users_roles.roles_inventory) — Identify roles with `bypass_rls`.

## Checklist
- Enable and force RLS on every table whose policies must apply to the owner.
- Map policy roles to the roles the application actually uses.
- Remove `BYPASSRLS` from application roles.
