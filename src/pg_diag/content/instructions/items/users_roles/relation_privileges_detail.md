# Relation Privileges Detail

This instruction belongs to report item `users_roles.relation_privileges_detail`. The item is backed by `roles.relation_privileges_detail` (SQL query).

## What this item shows
- One row per sampled relation and grantee with the granted `privileges`, the subset in `grantable_privileges`, and the `grantors`.
- Relation kind, owner, `relpages`, and `grantee_kind` for tables, partitioned tables, views, materialized views, foreign tables, and sequences.
- Owner entries are omitted because the owner holds every privilege.

## What to watch
- Large or sensitive tables readable by `PUBLIC` or by broad group roles.
- Grantors that are application accounts rather than owners or administrators.
- Sequences with `UPDATE` granted where only `USAGE` is required.

## Common fault causes
- Per-table grants issued by developers during incidents.
- Views created to restrict access while the underlying tables remain readable.
- Privileges inherited from default privileges of the wrong defining role.

## Automatic evaluation
- This item is an inventory and assigns no risk to individual rows.
- Stored relations are sampled by descending `relpages` (3,000) and other relations by name (3,000); the result is bounded to 3,000 rows. `candidate_sample_truncated` and `result_truncated` mark partial coverage, add a `[coverage]` row, and set the item severity to `unknown`.

## Related report items
- [users_roles.object_privileges_by_grantee](#item-users_roles.object_privileges_by_grantee) — Start from the aggregated matrix to find roles worth drilling into.
- [users_roles.column_privileges](#item-users_roles.column_privileges) — Check column-level exceptions on the same relations.
- [object_workload.excessive_dml_privileges](#item-object_workload.excessive_dml_privileges) — Review broad DML privileges flagged as risks.

## Checklist
- Query `pg_class.relacl` directly for relations outside the sample.
- Revoke privileges granted by non-administrative grantors.
- Align relation privileges with the group-based access model.
