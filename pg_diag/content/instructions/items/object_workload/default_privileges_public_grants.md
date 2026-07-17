# Default Privileges Public Grants

This instruction belongs to report item `object_workload.default_privileges_public_grants`.

This item reports `ALTER DEFAULT PRIVILEGES` entries that grant future-object privileges to `PUBLIC` or allow onward grants.

## What this item shows
- Owner, schema scope, and object type affected by default privileges.
- Future-object privileges granted to `PUBLIC`.
- Grantable default privileges held by non-owner roles.

## What to watch
- Findings that conflict with the approved ownership, privilege, or application-role baseline.
- Broad or unexpected access paths that can be combined with inherited role membership.

## Common fault causes
- Legacy grants or ownership left by migrations, role changes, extension upgrades, or manual administration.
- Intentional exceptions that were not documented or revalidated.

## Automatic evaluation

- `high`: future object privileges are granted to PUBLIC.
- `medium`: a non-owner can grant a default privilege onward.
- The check applies only to explicit default-privilege entries, not existing object ACLs.

## Related report items
- [cluster_inventory.public_schema_privileges](#item-cluster_inventory.public_schema_privileges) — Review public access at schema level.
- [object_workload.direct_user_grants](#item-object_workload.direct_user_grants) — Check explicit grants created alongside defaults.
- [object_workload.excessive_dml_privileges](#item-object_workload.excessive_dml_privileges) — Find broad object privileges resulting from defaults.

## Checklist
- Revoke default PUBLIC grants that are not explicitly required.
- Keep future-object privileges scoped to application and migration roles.
- Review default privileges after schema ownership or deployment changes.
