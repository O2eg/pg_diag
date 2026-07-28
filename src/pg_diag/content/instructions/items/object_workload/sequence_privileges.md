# Sequence Privileges

This instruction belongs to report item `object_workload.sequence_privileges`.

This item reports PUBLIC or grantable privileges on user-defined sequences.

## What this item shows
- Sequence privileges granted to `PUBLIC`.
- Grantable sequence privileges held by non-owner roles.
- Higher risk for `USAGE` or `UPDATE` grants to `PUBLIC`.

## What to watch
- Findings that conflict with the approved ownership, privilege, or application-role baseline.
- Broad or unexpected access paths that can be combined with inherited role membership.

## Common fault causes
- Legacy grants or ownership left by migrations, role changes, extension upgrades, or manual administration.
- Intentional exceptions that were not documented or revalidated.

## Automatic evaluation

- `high`: PUBLIC can use or advance a user sequence.
- `medium`: another sequence privilege is PUBLIC or can be granted onward.
- Ordinary explicit non-grantable role access is not included.
- At most 10,000 sequences in stable schema/name order are considered and at most 3,000 matching ACL findings are expanded.
- At most 1,000 findings are displayed. `candidate_sample_truncated`, `acl_expansion_truncated`, and `result_truncated` identify incomplete coverage, including through a `[coverage]` row when no ordinary finding survives.

## Related report items
- [object_workload.sequence_table_owner_mismatch](#item-object_workload.sequence_table_owner_mismatch) — Check ownership alignment with related tables.
- [object_workload.direct_user_grants](#item-object_workload.direct_user_grants) — Review direct sequence grants.
- [storage_vacuum.sequence_status](#item-storage_vacuum.sequence_status) — Inspect exhaustion risk for exposed sequences.

## Checklist
- Revoke unnecessary sequence privileges from `PUBLIC`.
- Grant sequence access only to roles that need to read or advance sequence values.
- Review sequence privileges together with table DML privileges.
