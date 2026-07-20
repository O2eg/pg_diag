# Direct User Grants

This instruction belongs to report item `object_workload.direct_user_grants`.

This item lists object privileges granted directly to login roles.

## What this item shows
- Object, owner, grantee login role, privilege, and grant option flag.
- Schema, relation, sequence, and function grants.

## What to watch
- Findings that conflict with the approved ownership, privilege, or application-role baseline.
- Broad or unexpected access paths that can be combined with inherited role membership.

## Common fault causes
- Legacy grants or ownership left by migrations, role changes, extension upgrades, or manual administration.
- Intentional exceptions that were not documented or revalidated.

## Automatic evaluation

- Severity is `unknown`: direct grants are a governance-policy question, not a PostgreSQL correctness failure.
- Results are bounded to 1000 grants and must be compared with the role-management baseline.

## Related report items
- [cluster_inventory.privilege_surface_by_role](#item-cluster_inventory.privilege_surface_by_role) — Review effective privileges after role inheritance.
- [object_workload.excessive_dml_privileges](#item-object_workload.excessive_dml_privileges) — Identify overly broad direct DML grants.
- [object_workload.unused_privileged_grants](#item-object_workload.unused_privileged_grants) — Check direct grants without observed use.

## Checklist
- Prefer grants to group roles instead of individual login users.
- Move one-off direct grants into auditable role membership.
- Revoke direct grants that no longer match operational needs.
