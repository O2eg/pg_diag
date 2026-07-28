# Schema Owner Drift

This instruction belongs to report item `object_workload.schema_owner_drift`.

This item lists sampled user objects whose owner differs from their containing schema owner.

## What this item shows
- Object kind, schema, object name, object owner, and schema owner.
- Objects from PostgreSQL system schemas are excluded.
- Stored tables and materialized views are sampled from the 10,000 largest non-empty relations; partitioned tables, sequences, views, and foreign tables from 10,000 names; functions from the 1,000 most-called candidates.

## What to watch
- Findings that conflict with the approved ownership, privilege, or application-role baseline.
- Broad or unexpected access paths that can be combined with inherited role membership.

## Common fault causes
- Legacy grants or ownership left by migrations, role changes, extension upgrades, or manual administration.
- Intentional exceptions that were not documented or revalidated.

## Automatic evaluation

- Severity is `unknown` until the result is compared with the intended owner-role matrix.
- Output is bounded to 1,000 objects and is not a complete database-wide inventory.
- `candidate_sample_truncated` identifies a reached root limit; because extension ownership is checked later, extension-owned roots can consume part of that truncated sample. `result_truncated` covers the final output limit. A `[coverage]` row prevents either condition from appearing clean.

## Related report items
- [object_workload.database_owner_mismatch](#item-object_workload.database_owner_mismatch) — Compare schema and database ownership.
- [object_workload.object_owner_drift](#item-object_workload.object_owner_drift) — Review objects owned outside the schema baseline.
- [cluster_inventory.schema_privilege_matrix](#item-cluster_inventory.schema_privilege_matrix) — Check privileges granted within affected schemas.

## Checklist
- Verify whether the schema owner should also own contained objects.
- Fix accidental drift from manual DDL or migrations run under the wrong role.
- Keep exceptions documented for shared schemas.
