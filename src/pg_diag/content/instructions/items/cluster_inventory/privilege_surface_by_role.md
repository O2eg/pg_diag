# Privilege Surface By Role

This instruction belongs to report item `cluster_inventory.privilege_surface_by_role`.

This item summarizes a bounded sample of explicit object privileges by grantee role.

## What this item shows
- Sampled explicit privilege count per role.
- Sampled counts by schema, relation, sequence, and function.
- Sampled grant option count and privilege type list.

## What to watch
- Findings whose severity or evidence differs from the approved cluster security baseline.
- Broad access, weak authentication, sensitive-file exposure, or missing controls that compound other findings.

## Common fault causes
- Package or cloud defaults, legacy compatibility, incomplete hardening, or undocumented operational exceptions.
- A change in one security layer without corresponding role, HBA, filesystem, or extension controls.

## Automatic evaluation

- `medium`: the grantee is PUBLIC or at least one explicit privilege is grantable onward.
- `unknown`: all other counts require comparison with the intended access-control baseline.
- Counts cover only the bounded ACL sample, not every ACL entry in the connected database and not effective inherited privileges.
- Relations are selected before ACL expansion; stored relations are prioritized by `relpages`, functions by `pg_stat_user_functions.calls`, and named non-storage objects by stable name order.
- At most 1,000 expanded ACL rows are taken from each of the relation, function, and schema pools.
- `candidate_sample_truncated`, `acl_expansion_truncated`, and `result_truncated` identify incomplete coverage. A `[coverage]` row remains visible when truncation produces no ordinary role row.

## Related report items
- [cluster_inventory.predefined_admin_role_membership](#item-cluster_inventory.predefined_admin_role_membership) — Review predefined administrative inheritance.
- [object_workload.direct_user_grants](#item-object_workload.direct_user_grants) — Identify object privileges granted directly.
- [object_workload.excessive_dml_privileges](#item-object_workload.excessive_dml_privileges) — Find broad DML access in the role surface.

## Checklist
- Sort by privilege count to find broad roles.
- Review PUBLIC and login-role footprints first.
- Reduce direct object grants through group roles.
