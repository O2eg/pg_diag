# Database Owner Mismatch

This instruction belongs to report item `object_workload.database_owner_mismatch`.

This item lists user objects whose owner differs from the connected database owner.

## What this item shows
- User schemas, relations, sequences, views, and functions.
- Current object owner and database owner.
- Extension-owned objects are excluded.

## What to watch
- Findings that conflict with the approved ownership, privilege, or application-role baseline.
- Broad or unexpected access paths that can be combined with inherited role membership.

## Common fault causes
- Legacy grants or ownership left by migrations, role changes, extension upgrades, or manual administration.
- Intentional exceptions that were not documented or revalidated.

## Automatic evaluation

- Severity is `unknown`: dedicated database, schema, migration, and application owner roles commonly differ by design.
- Output is bounded to 1000 objects; absence from a truncated result is not proof of ownership alignment.

## Related report items
- [object_workload.schema_owner_drift](#item-object_workload.schema_owner_drift) — Review schema ownership under the database.
- [cluster_inventory.privileged_roles](#item-cluster_inventory.privileged_roles) — Inspect unexpected or privileged database owners.
- [cluster_inventory.schema_privilege_matrix](#item-cluster_inventory.schema_privilege_matrix) — Review effective schema access.

## Checklist
- Treat this as an ownership hygiene review, not an automatic failure.
- Document expected app, migration, and owner roles.
- Move unexpected ownership to the approved role set.
