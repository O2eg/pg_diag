# Grant Option Holders

This instruction belongs to report item `object_workload.grant_option_holders`.

This item lists non-owner roles that can re-grant object privileges.

## What this item shows
- Object, owner, grantee, privilege, and whether the grantee can login.
- Schema, relation, sequence, and function privileges with grant option.

## What to watch
- Findings that conflict with the approved ownership, privilege, or application-role baseline.
- Broad or unexpected access paths that can be combined with inherited role membership.

## Common fault causes
- Legacy grants or ownership left by migrations, role changes, extension upgrades, or manual administration.
- Intentional exceptions that were not documented or revalidated.

## Automatic evaluation

- `medium` is raised for non-owner grant options because they expand who can delegate access.
- Owner and approved administration roles may be intentional exceptions.
- Results are bounded to 1000 grants.

## Related report items
- [object_workload.direct_user_grants](#item-object_workload.direct_user_grants) — Review grants issued directly to users.
- [cluster_inventory.privilege_surface_by_role](#item-cluster_inventory.privilege_surface_by_role) — Inspect the holder's complete privilege surface.
- [object_workload.object_acl_drift](#item-object_workload.object_acl_drift) — Check ACL changes associated with grant propagation.

## Checklist
- Keep `WITH GRANT OPTION` limited to owner or controlled administration roles.
- Review login roles with grant option first.
- Revoke unintended grant option privileges.
