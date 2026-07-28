# Orphaned Object Owners

This instruction belongs to report item `object_workload.orphaned_object_owners`.

This item reports no-login roles that own objects in bounded candidate pools and need verification.

## What this item shows
- Owner role name.
- Whether the owner can login or is superuser.
- Number of sampled user objects owned by the role.
- Stored tables and materialized views are sampled from the 10,000 largest non-empty relations; partitioned tables, sequences, views, and foreign tables from 10,000 names; functions from the 1,000 most-called candidates.

## What to watch
- Findings that conflict with the approved ownership, privilege, or application-role baseline.
- Broad or unexpected access paths that can be combined with inherited role membership.

## Common fault causes
- Legacy grants or ownership left by migrations, role changes, extension upgrades, or manual administration.
- Intentional exceptions that were not documented or revalidated.

## Automatic evaluation

- Severity is `unknown`: no-login ownership is normally desirable privilege separation and does not mean a role is orphaned.
- A finding becomes actionable only when the role is absent from the ownership baseline or operational process.
- `sampled_object_count` is not a database-wide ownership count.
- `candidate_sample_truncated` identifies a reached root limit; because extension ownership is checked later, extension-owned roots can consume part of that truncated sample. `result_truncated` covers the final 1,000-owner limit. A `[coverage]` row prevents either condition from appearing clean.

## Related report items
- [object_workload.object_owner_drift](#item-object_workload.object_owner_drift) — Review broader ownership drift.
- [cluster_inventory.privileged_roles](#item-cluster_inventory.privileged_roles) — Confirm whether replacement ownership should use a controlled role.

## Checklist
- Confirm that each no-login owner role is intentional and managed.
- Reassign objects owned by deprecated roles.
- Keep ownership roles separate from login roles where possible.
