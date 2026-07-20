# Schema Privilege Matrix

This instruction belongs to report item `cluster_inventory.schema_privilege_matrix`.

This item shows schema owner, grantee, `USAGE`, `CREATE`, and object counts for user schemas.

## What this item shows
- One row per schema/grantee.
- Schema-level `USAGE`, `CREATE`, and grant option flags.
- Table, sequence, view, and function counts in the schema.

## What to watch
- Findings whose severity or evidence differs from the approved cluster security baseline.
- Broad access, weak authentication, sensitive-file exposure, or missing controls that compound other findings.

## Common fault causes
- Package or cloud defaults, legacy compatibility, incomplete hardening, or undocumented operational exceptions.
- A change in one security layer without corresponding role, HBA, filesystem, or extension controls.

## Automatic evaluation

- `high`: PUBLIC can CREATE objects in a user schema.
- `medium`: PUBLIC has another schema privilege or a privilege is grantable onward.
- Owner and explicit role rows are informational; effective inherited privileges are not expanded.

## Related report items
- [cluster_inventory.public_schema_privileges](#item-cluster_inventory.public_schema_privileges) — Review exposure through the public schema.
- [cluster_inventory.non_public_schema_privileges](#item-cluster_inventory.non_public_schema_privileges) — Review grants on application schemas.
- [object_workload.schema_owner_drift](#item-object_workload.schema_owner_drift) — Compare grants with schema ownership.

## Checklist
- Remove unexpected PUBLIC `CREATE`.
- Verify schema owner roles match the deployment model.
- Use the matrix to spot schemas with unusually broad access.
