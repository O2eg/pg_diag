# Object Privileges By Grantee

This instruction belongs to report item `users_roles.object_privileges_by_grantee`. The item is backed by `roles.object_privileges_by_grantee` (SQL query).

## What this item shows
- Explicit object privileges in the connected database aggregated by `grantee_name`, `grantee_kind` (`login role`, `group role`, or `PUBLIC`), `schema_name`, `object_kind`, and `privilege_type`.
- `object_count` is the number of sampled objects carrying that privilege and `grantable_object_count` the subset granted `WITH GRANT OPTION`.
- Object kinds cover tables, partitioned tables, views, materialized views, foreign tables, sequences, functions, types, and domains. Owner entries are omitted because the owner holds every privilege.
- Objects that share an identical ACL are expanded once, so the counts stay exact for the sampled objects while ACL expansion stays bounded.

## What to watch
- Login roles with direct object privileges instead of privileges through group roles.
- `PUBLIC` with DML privileges or `EXECUTE` on application functions.
- Group roles whose privilege footprint does not match their documented purpose.
- Any `grantable_object_count` above zero for non-administrative roles.

## Common fault causes
- `GRANT ... ON ALL TABLES IN SCHEMA` applied to users during onboarding.
- Default privileges that grant to `PUBLIC` or to individual users.
- Privileges not revoked after a role changed responsibilities.

## Automatic evaluation
- This item is an inventory and assigns no risk to individual privilege rows.
- Stored relations are sampled by descending `relpages` (10,000), other relations by name (10,000), functions by call count (1,000), and types by name (1,000); ACL expansion is bounded to 3,000 rows per pool and the result to 3,000 rows. `candidate_sample_truncated`, `acl_expansion_truncated`, and `result_truncated` mark partial coverage, add a `[coverage]` row, and set the item severity to `unknown`.

## Related report items
- [users_roles.relation_privileges_detail](#item-users_roles.relation_privileges_detail) — Drill down to individual relations and grantors.
- [object_workload.direct_user_grants](#item-object_workload.direct_user_grants) — Review privileges granted directly to login roles.
- [cluster_inventory.privilege_surface_by_role](#item-cluster_inventory.privilege_surface_by_role) — Compare with the risk-oriented privilege surface summary.
- [users_roles.default_privileges](#item-users_roles.default_privileges) — Check which default privileges keep producing these grants.

## Checklist
- Filter by `grantee_kind` to compare users, groups, and `PUBLIC` separately.
- Move privileges from login roles to group roles.
- Revoke `PUBLIC` privileges that the application does not need.
