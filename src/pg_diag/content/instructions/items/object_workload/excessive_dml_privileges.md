# Excessive DML Privileges

This instruction belongs to report item `object_workload.excessive_dml_privileges`.

This item lists PUBLIC or grantable DML privileges on non-system tables in the connected database.

## What this item shows
- `INSERT`, `UPDATE`, `DELETE`, or `TRUNCATE` granted to `PUBLIC`.
- DML privileges that can be granted onward.
- Table owner and grantee context for each finding.

## What to watch
- Findings that conflict with the approved ownership, privilege, or application-role baseline.
- Broad or unexpected access paths that can be combined with inherited role membership.

## Common fault causes
- Legacy grants or ownership left by migrations, role changes, extension upgrades, or manual administration.
- Intentional exceptions that were not documented or revalidated.

## Automatic evaluation

- `high`: PUBLIC has a write privilege on a user table.
- `medium`: a non-owner can grant DML privileges onward.
- Review inherited role membership separately; this item evaluates object ACL entries.
- ACLs are read directly from PostgreSQL catalogs rather than the current role's information-schema visibility subset.
- Stored relations are selected from the 10,000 largest non-empty tables by `relpages`; partitioned tables, views, and foreign tables use a separate 10,000-row alphabetical pool.
- At most 3,000 matching ACL rows are evaluated and 1,000 findings displayed, so absence is not proof that every relation was covered.
- `candidate_sample_truncated`, `acl_expansion_truncated`, and `result_truncated` make that incomplete coverage explicit; a `[coverage]` row remains visible when no ordinary finding survives.

## Related report items
- [object_workload.direct_user_grants](#item-object_workload.direct_user_grants) — Identify privileges granted directly to login roles.
- [cluster_inventory.privilege_surface_by_role](#item-cluster_inventory.privilege_surface_by_role) — Review the role's effective privilege surface.
- [object_workload.unused_privileged_grants](#item-object_workload.unused_privileged_grants) — Check whether elevated grants appear unused.

## Checklist
- Revoke DML privileges from `PUBLIC` unless explicitly required.
- Avoid grantable DML privileges for application roles.
- Confirm each listed grant has a current business owner and purpose.
