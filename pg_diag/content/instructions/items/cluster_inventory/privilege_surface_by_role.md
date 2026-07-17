# Privilege Surface By Role

This instruction belongs to report item `cluster_inventory.privilege_surface_by_role`.

This item summarizes explicit object privileges by grantee role.

## What this item shows
- Explicit privilege count per role.
- Counts by schema, relation, sequence, and function.
- Grant option count and privilege type list.

## What to watch
- Findings whose severity or evidence differs from the approved cluster security baseline.
- Broad access, weak authentication, sensitive-file exposure, or missing controls that compound other findings.

## Common fault causes
- Package or cloud defaults, legacy compatibility, incomplete hardening, or undocumented operational exceptions.
- A change in one security layer without corresponding role, HBA, filesystem, or extension controls.

## Automatic evaluation

- `medium`: the grantee is PUBLIC or at least one explicit privilege is grantable onward.
- `unknown`: all other counts require comparison with the intended access-control baseline.
- Counts cover explicit ACL entries in the connected database, not effective inherited privileges.

## Related report items
- [cluster_inventory.predefined_admin_role_membership](#item-cluster_inventory.predefined_admin_role_membership) — Review predefined administrative inheritance.
- [object_workload.direct_user_grants](#item-object_workload.direct_user_grants) — Identify object privileges granted directly.
- [object_workload.excessive_dml_privileges](#item-object_workload.excessive_dml_privileges) — Find broad DML access in the role surface.

## Checklist
- Sort by privilege count to find broad roles.
- Review PUBLIC and login-role footprints first.
- Reduce direct object grants through group roles.
