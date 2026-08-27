# Database Privileges

This instruction belongs to report item `users_roles.database_privileges`. The item is backed by `roles.database_privileges` (SQL query).

## What this item shows
- `CONNECT`, `CREATE`, and `TEMPORARY` privileges on every database by grantee, with `grantee_kind` (`login role`, `group role`, or `PUBLIC`), `is_grantable`, and the grantor.
- `acl_is_default` marks databases without an explicit ACL; PostgreSQL then grants `CONNECT` and `TEMPORARY` to `PUBLIC`.
- Owner entries are omitted because the owner holds every privilege.

## What to watch
- `PUBLIC` with `CONNECT` on production databases; every login role can then reach the database and only `pg_hba.conf` limits access.
- `CREATE` on a database granted to application roles, which allows new schemas.
- Grantable database privileges held by non-administrative roles.

## Common fault causes
- Databases created without `REVOKE CONNECT ON DATABASE ... FROM PUBLIC`.
- Access granted to `PUBLIC` to simplify onboarding.
- Privileges granted to individual users instead of groups.

## Automatic evaluation
- This item is an inventory and assigns no risk to individual privileges.
- The list covers 1,000 databases and 3,000 ACL entries; `candidate_sample_truncated` and `acl_expansion_truncated` mark partial coverage and set the item severity to `unknown`.

## Related report items
- [users_roles.hba_rules](#item-users_roles.hba_rules) — Check which authentication rules admit the grantees.
- [cluster_inventory.schema_privilege_matrix](#item-cluster_inventory.schema_privilege_matrix) — Continue with schema privileges inside the database.
- [users_roles.object_privileges_by_grantee](#item-users_roles.object_privileges_by_grantee) — Continue with object privileges by grantee.

## Checklist
- Revoke `CONNECT` from `PUBLIC` on databases with restricted access.
- Grant database privileges to group roles rather than users.
- Record the intended owner and grantees of each database.
