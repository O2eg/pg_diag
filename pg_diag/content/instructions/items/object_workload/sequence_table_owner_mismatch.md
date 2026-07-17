# Sequence Table Owner Mismatch

This instruction belongs to report item `object_workload.sequence_table_owner_mismatch`.

This item lists owned sequences whose owner differs from the dependent table owner.

## What this item shows
- Sequence schema/name and owner.
- Dependent table and column.
- Table owner.

## What to watch
- Findings that conflict with the approved ownership, privilege, or application-role baseline.
- Broad or unexpected access paths that can be combined with inherited role membership.

## Common fault causes
- Legacy grants or ownership left by migrations, role changes, extension upgrades, or manual administration.
- Intentional exceptions that were not documented or revalidated.

## Automatic evaluation

- Severity is `unknown`: different owners may be intentional and do not by themselves prevent sequence use.
- Results are bounded to 1000 dependencies; validate privileges and the migration ownership model.

## Related report items
- [object_workload.sequence_privileges](#item-object_workload.sequence_privileges) — Review access to the affected sequence.
- [object_workload.object_owner_drift](#item-object_workload.object_owner_drift) — Check broader ownership inconsistencies.
- [storage_vacuum.sequence_status](#item-storage_vacuum.sequence_status) — Inspect the sequence's capacity and usage risk.

## Checklist
- Align sequence and table ownership for application-owned tables.
- Review identity and serial columns after ownership changes.
- Re-run grants where sequence privileges are required by application roles.
