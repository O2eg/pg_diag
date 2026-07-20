# Orphaned Object Owners

This instruction belongs to report item `object_workload.orphaned_object_owners`.

This item reports no-login roles that own user objects and need verification.

## What this item shows
- Owner role name.
- Whether the owner can login or is superuser.
- Number of user objects owned by the role.

## What to watch
- Findings that conflict with the approved ownership, privilege, or application-role baseline.
- Broad or unexpected access paths that can be combined with inherited role membership.

## Common fault causes
- Legacy grants or ownership left by migrations, role changes, extension upgrades, or manual administration.
- Intentional exceptions that were not documented or revalidated.

## Automatic evaluation

- Severity is `unknown`: no-login ownership is normally desirable privilege separation and does not mean a role is orphaned.
- A finding becomes actionable only when the role is absent from the ownership baseline or operational process.

## Related report items
- [object_workload.object_owner_drift](#item-object_workload.object_owner_drift) — Review broader ownership drift.
- [cluster_inventory.privileged_roles](#item-cluster_inventory.privileged_roles) — Confirm whether replacement ownership should use a controlled role.

## Checklist
- Confirm that each no-login owner role is intentional and managed.
- Reassign objects owned by deprecated roles.
- Keep ownership roles separate from login roles where possible.
