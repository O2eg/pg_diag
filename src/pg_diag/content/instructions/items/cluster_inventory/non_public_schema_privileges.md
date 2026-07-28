# Non-Public Schema Privileges

This instruction belongs to report item `cluster_inventory.non_public_schema_privileges`.

This item reports risky grants on non-system schemas other than `public`.

## What this item shows
- `PUBLIC` privileges on application schemas.
- Non-owner `CREATE` privileges on schemas.
- Grantable schema privileges held by non-owner roles.

## What to watch
- Findings whose severity or evidence differs from the approved cluster security baseline.
- Broad access, weak authentication, sensitive-file exposure, or missing controls that compound other findings.

## Common fault causes
- Package or cloud defaults, legacy compatibility, incomplete hardening, or undocumented operational exceptions.
- A change in one security layer without corresponding role, HBA, filesystem, or extension controls.

## Automatic evaluation

- `high`: PUBLIC can CREATE in a non-system schema.
- `medium`: a non-owner can CREATE or re-grant privileges.
- `unknown`: PUBLIC has only another privilege such as USAGE; compare it with the schema baseline.
- At most 10,000 schemas in stable name order are considered and at most 3,000 matching ACL findings are expanded.
- At most 1,000 findings are displayed. `candidate_sample_truncated`, `acl_expansion_truncated`, and `result_truncated` identify incomplete coverage; a `[coverage]` row prevents truncation from appearing as a clean `empty` result.

## Related report items
- [cluster_inventory.schema_privilege_matrix](#item-cluster_inventory.schema_privilege_matrix) — Review the bounded sample of grants across schemas and roles.
- [object_workload.schema_owner_drift](#item-object_workload.schema_owner_drift) — Compare privileges with expected schema owners.
- [cluster_inventory.public_schema_privileges](#item-cluster_inventory.public_schema_privileges) — Contrast application-schema and public exposure.

## Checklist
- Revoke broad schema privileges from `PUBLIC`.
- Keep schema `CREATE` privileges limited to owners or migration roles.
- Review schema grants after extension installation and migrations.
