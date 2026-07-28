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
- Results are bounded to 1,000 displayed grants.
- Stored relations are selected by descending `relpages`, functions by descending calls, and named non-storage objects by stable name order before ACL expansion.
- Relation, function, and schema ACL expansion is capped at 1,000 rows per pool.
- Extension ownership is checked only after each bounded root set is selected. If that root limit is reached, `candidate_sample_truncated = true` warns that extension-owned roots removed later may have occupied places ahead of unchecked user-owned objects.
- `candidate_sample_truncated`, `acl_expansion_truncated`, and `result_truncated` identify incomplete coverage; a `[coverage]` row prevents truncation from appearing as a clean `empty` result.

## Related report items
- [object_workload.direct_user_grants](#item-object_workload.direct_user_grants) — Review grants issued directly to users.
- [cluster_inventory.privilege_surface_by_role](#item-cluster_inventory.privilege_surface_by_role) — Inspect the holder's bounded sampled privilege surface.
- [object_workload.object_acl_drift](#item-object_workload.object_acl_drift) — Check ACL changes associated with grant propagation.

## Checklist
- Keep `WITH GRANT OPTION` limited to owner or controlled administration roles.
- Review login roles with grant option first.
- Revoke unintended grant option privileges.
