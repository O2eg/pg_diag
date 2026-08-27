# Object Ownership By Role

This instruction belongs to report item `users_roles.object_ownership_by_role`. The item is backed by `roles.object_ownership_by_role` (SQL query).

## What this item shows
- For each owner role: owned databases and tablespaces cluster-wide, and sampled counts of owned schemas, tables, partitioned tables, views, materialized views, foreign tables, sequences, and functions in the connected database.
- `sampled_relpages` sums the pages of sampled stored relations and approximates how much data a role owns.

## What to watch
- Login roles or superusers that own application objects; ownership should normally belong to a dedicated `NOLOGIN` owner role.
- Objects owned by many different roles inside one schema, which complicates DDL and migrations.
- Empty group roles that still own objects and therefore cannot be dropped.

## Common fault causes
- Objects created by whichever account ran the migration instead of a fixed owner role.
- Schemas created by superusers during troubleshooting.
- Ownership never reassigned after a role was deprecated.

## Automatic evaluation
- This item is an inventory and assigns no risk to individual owners.
- Stored relations are sampled by descending `relpages` (10,000), other relations by name (10,000), functions by call count (1,000), and schemas by name (10,000); `candidate_sample_truncated` and `result_truncated` mark partial coverage and set the item severity to `unknown`.

## Related report items
- [object_workload.superuser_owned_user_objects](#item-object_workload.superuser_owned_user_objects) — Review specific objects owned by superusers.
- [object_workload.orphaned_object_owners](#item-object_workload.orphaned_object_owners) — Review objects owned by no-login roles.
- [users_roles.group_roles_without_members](#item-users_roles.group_roles_without_members) — Check empty groups that still own objects.

## Checklist
- Use `REASSIGN OWNED` or `ALTER ... OWNER TO` to consolidate ownership on dedicated owner roles.
- Treat sampled counts as partial when coverage flags are set.
- Verify ownership of specific objects with `pg_class.relowner` before changing it.
