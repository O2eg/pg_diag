# Public Schema Privileges

This instruction belongs to report item `cluster_inventory.public_schema_privileges`.

This item lists risky grants on schema `public` in the connected database.

## What this item shows
- `PUBLIC CREATE` on schema `public`.
- Non-owner `CREATE` privileges that allow object creation in `public`.
- Grantable non-owner schema privileges.

## What to watch
- Findings whose severity or evidence differs from the approved cluster security baseline.
- Broad access, weak authentication, sensitive-file exposure, or missing controls that compound other findings.

## Common fault causes
- Package or cloud defaults, legacy compatibility, incomplete hardening, or undocumented operational exceptions.
- A change in one security layer without corresponding role, HBA, filesystem, or extension controls.

## Automatic evaluation

- `high`: PUBLIC can CREATE objects in schema `public`, enabling name-shadowing risk in unsafe search paths.
- `medium`: a non-owner can CREATE or re-grant schema privileges.
- PostgreSQL version and upgraded-database defaults can differ, so evaluate the effective ACL shown.
- ACL expansion is capped at 3,000 matching risky grants after the finding predicate is applied.
- `acl_expansion_truncated = true` and the `[coverage]` row identify an incomplete ACL expansion; such output is not a clean result.

## Related report items
- [cluster_inventory.non_public_schema_privileges](#item-cluster_inventory.non_public_schema_privileges) — Compare public and application-schema grants.
- [object_workload.default_privileges_public_grants](#item-object_workload.default_privileges_public_grants) — Check defaults that recreate public access.
- [cluster_inventory.schema_privilege_matrix](#item-cluster_inventory.schema_privilege_matrix) — Review the bounded schema privilege matrix.

## Checklist
- Revoke `CREATE` on schema `public` from `PUBLIC`.
- Keep object creation limited to schema owners or migration roles.
- Review grants after application or extension installation.
