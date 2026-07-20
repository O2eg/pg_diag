# Object Owner Drift

This instruction belongs to report item `object_workload.object_owner_drift`.

This item reports schemas where same-kind objects are owned by multiple roles.

## What this item shows
- Schema and object kind.
- Number of objects and distinct owners.
- Whether any object in the group is owned by a superuser.

## What to watch
- Findings that conflict with the approved ownership, privilege, or application-role baseline.
- Broad or unexpected access paths that can be combined with inherited role membership.

## Common fault causes
- Legacy grants or ownership left by migrations, role changes, extension upgrades, or manual administration.
- Intentional exceptions that were not documented or revalidated.

## Automatic evaluation

- Severity is `unknown`: mixed owners are not intrinsically unsafe without an approved ownership baseline.
- Treat superuser-owned rows separately using the dedicated superuser ownership item.

## Related report items
- [object_workload.orphaned_object_owners](#item-object_workload.orphaned_object_owners) — Find objects whose owner role no longer exists.
- [object_workload.superuser_owned_user_objects](#item-object_workload.superuser_owned_user_objects) — Identify user objects owned by superusers.
- [object_workload.schema_owner_drift](#item-object_workload.schema_owner_drift) — Compare object and schema ownership posture.

## Checklist
- Pick an expected owner role per application schema.
- Normalize object ownership after migrations.
- Investigate superuser-owned objects first.
