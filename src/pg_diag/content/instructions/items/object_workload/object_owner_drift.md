# Object Owner Drift

This instruction belongs to report item `object_workload.object_owner_drift`.

This item reports schemas where same-kind objects in bounded candidate pools are owned by multiple roles.

## What this item shows
- Schema and object kind.
- Number of sampled objects and distinct owners.
- Whether any sampled object in the group is owned by a superuser.
- Stored tables and materialized views are sampled from the 10,000 largest non-empty relations; partitioned tables, sequences, views, and foreign tables from 10,000 names; functions from the 1,000 most-called candidates.

## What to watch
- Findings that conflict with the approved ownership, privilege, or application-role baseline.
- Broad or unexpected access paths that can be combined with inherited role membership.

## Common fault causes
- Legacy grants or ownership left by migrations, role changes, extension upgrades, or manual administration.
- Intentional exceptions that were not documented or revalidated.

## Automatic evaluation

- Severity is `unknown`: mixed owners are not intrinsically unsafe without an approved ownership baseline.
- Treat superuser-owned rows separately using the dedicated superuser ownership item.
- Counts describe the bounded sample, not the complete database object population.
- `candidate_sample_truncated` identifies a reached root limit; because extension ownership is checked later, extension-owned roots can consume part of that truncated sample. `result_truncated` covers the final 1,000-group limit. A `[coverage]` row prevents either condition from appearing clean.

## Related report items
- [object_workload.orphaned_object_owners](#item-object_workload.orphaned_object_owners) — Find objects whose owner role no longer exists.
- [object_workload.superuser_owned_user_objects](#item-object_workload.superuser_owned_user_objects) — Identify user objects owned by superusers.
- [object_workload.schema_owner_drift](#item-object_workload.schema_owner_drift) — Compare object and schema ownership posture.

## Checklist
- Pick an expected owner role per application schema.
- Normalize object ownership after migrations.
- Investigate superuser-owned objects first.
