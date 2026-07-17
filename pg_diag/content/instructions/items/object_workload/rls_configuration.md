# Row Level Security Configuration

This instruction belongs to report item `object_workload.rls_configuration`.

This item reports RLS configurations that are inactive, incomplete, or not forced for table owners.

## What this item shows
- Tables with policies but disabled RLS.
- Tables with RLS enabled but no policies.
- Tables where RLS is not forced for table owners.

## What to watch
- Findings that conflict with the approved ownership, privilege, or application-role baseline.
- Broad or unexpected access paths that can be combined with inherited role membership.

## Common fault causes
- Legacy grants or ownership left by migrations, role changes, extension upgrades, or manual administration.
- Intentional exceptions that were not documented or revalidated.

## Automatic evaluation

- `high`: policies exist while RLS itself is disabled.
- `unknown`: RLS is not forced for the table owner; compare that normal default with the application threat model.
- RLS enabled with no policies is `ok` because PostgreSQL applies default deny to affected non-bypass roles.

## Related report items
- [object_workload.rls_table_privilege_mismatch](#item-object_workload.rls_table_privilege_mismatch) — Find table privileges that may bypass intended RLS posture.
- [object_workload.object_owner_drift](#item-object_workload.object_owner_drift) — Review owners that can bypass row policies.
- [object_workload.excessive_dml_privileges](#item-object_workload.excessive_dml_privileges) — Check broad DML access to protected tables.

## Checklist
- Enable RLS when policies exist.
- Add explicit policies when access should be allowed; an empty policy set intentionally denies access.
- Use `FORCE ROW LEVEL SECURITY` where owners should also be constrained.
