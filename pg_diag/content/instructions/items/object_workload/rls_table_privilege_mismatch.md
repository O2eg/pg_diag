# RLS Table Privilege Mismatch

This instruction belongs to report item `object_workload.rls_table_privilege_mismatch`.

This item lists RLS-enabled tables with broad, grantable, or direct login-role table privileges.

## What this item shows
- RLS table, owner, grantee, privilege, and grant option flag.
- Whether `FORCE ROW LEVEL SECURITY` is enabled.

## What to watch
- Findings that conflict with the approved ownership, privilege, or application-role baseline.
- Broad or unexpected access paths that can be combined with inherited role membership.

## Common fault causes
- Legacy grants or ownership left by migrations, role changes, extension upgrades, or manual administration.
- Intentional exceptions that were not documented or revalidated.

## Automatic evaluation

- `medium`: access is PUBLIC or can be granted onward.
- `unknown`: a login role has a direct grant; RLS policy evaluation still applies and the access baseline decides whether this is drift.
- Results are bounded to 1000 grants.

## Related report items
- [object_workload.rls_configuration](#item-object_workload.rls_configuration) — Review row-policy enablement and force settings.
- [object_workload.excessive_dml_privileges](#item-object_workload.excessive_dml_privileges) — Check broad DML access to affected tables.
- [object_workload.object_owner_drift](#item-object_workload.object_owner_drift) — Review owners that can bypass RLS.

## Checklist
- Verify policies cover every role with table access.
- Avoid PUBLIC grants on RLS-protected tables.
- Use group roles and keep grant option tightly limited.
