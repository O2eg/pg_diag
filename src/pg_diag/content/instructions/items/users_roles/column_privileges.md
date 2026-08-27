# Column Privileges

This instruction belongs to report item `users_roles.column_privileges`. The item is backed by `roles.column_privileges` (SQL query).

## What this item shows
- Column-level privileges from `pg_attribute.attacl` for the largest sampled relations: schema, relation, column, grantee, `grantee_kind`, `privileges`, `grantable_privileges`, and `grantors`.
- Owner entries are omitted.

## What to watch
- Column grants used to expose parts of sensitive tables; they interact with table-level grants and views.
- `UPDATE` or `INSERT` column grants to reporting roles.
- Column grants on relations whose table-level privileges already include the same right, which makes the column grant redundant and misleading.

## Common fault causes
- Column-level access introduced for one consumer and never documented.
- Table-level grants added later that superseded the column restriction.

## Automatic evaluation
- This item is an inventory and assigns no risk to individual rows.
- Only the 5,000 largest relations are inspected and at most 3,000 column ACL rows are expanded; `candidate_sample_truncated`, `column_sample_truncated`, and `result_truncated` mark partial coverage, add a `[coverage]` row, and set the item severity to `unknown`.

## Related report items
- [users_roles.relation_privileges_detail](#item-users_roles.relation_privileges_detail) — Compare with the table-level privileges of the same relations.
- [users_roles.rls_policies_by_role](#item-users_roles.rls_policies_by_role) — Check row-level restrictions that complement column restrictions.

## Checklist
- Confirm that table-level grants do not override intended column restrictions.
- Prefer views or row-level security when many columns need different rules.
