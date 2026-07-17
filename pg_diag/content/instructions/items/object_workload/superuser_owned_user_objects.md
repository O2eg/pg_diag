# Superuser-Owned User Objects

This instruction belongs to report item `object_workload.superuser_owned_user_objects`.

This item lists user-defined objects owned by PostgreSQL superusers.

## What this item shows
- Tables, sequences, views, foreign tables, and functions outside system schemas.
- Object owner and whether the owner is a superuser.
- Extension-owned objects are excluded.

## What to watch
- Findings that conflict with the approved ownership, privilege, or application-role baseline.
- Broad or unexpected access paths that can be combined with inherited role membership.

## Common fault causes
- Legacy grants or ownership left by migrations, role changes, extension upgrades, or manual administration.
- Intentional exceptions that were not documented or revalidated.

## Automatic evaluation

- `medium` requests review because superuser ownership expands the impact of owner-controlled code and DDL.
- It is not automatically `high`: bootstrap or administrative ownership may be an intentional baseline exception.
- Results are bounded to 1000 objects.

## Related report items
- [object_workload.object_owner_drift](#item-object_workload.object_owner_drift) — Review ownership deviations from the application baseline.
- [cluster_inventory.privileged_roles](#item-cluster_inventory.privileged_roles) — Inspect the privileged owner role.
- [object_workload.security_definer_owner_drift](#item-object_workload.security_definer_owner_drift) — Check privileged function ownership.

## Checklist
- Move application objects to dedicated owner roles.
- Keep superuser ownership only for objects that truly require it.
- Recheck dependent grants after changing ownership.
