# Tablespace Privileges

This instruction belongs to report item `users_roles.tablespace_privileges`. The item is backed by `roles.tablespace_privileges` (SQL query).

## What this item shows
- Explicit `CREATE` privileges on tablespaces by grantee, with `grantee_kind`, `is_grantable`, and the grantor.
- Owner entries are omitted; tablespaces without an explicit ACL produce no rows.

## What to watch
- Application roles allowed to create objects in dedicated or fast tablespaces.
- `PUBLIC` with `CREATE` on a tablespace.
- Grantable tablespace privileges held by non-administrative roles.

## Common fault causes
- Tablespace privileges granted to a migration account and never revoked.
- Storage tiers exposed to every role instead of the owner role only.

## Automatic evaluation
- This item is an inventory and assigns no risk to individual privileges.
- The list covers 1,000 tablespaces and 3,000 ACL entries; coverage flags mark partial results and add a `[coverage]` row.

## Related report items
- [cluster_inventory.tablespaces](#item-cluster_inventory.tablespaces) — Review tablespace locations and owners.
- [users_roles.database_privileges](#item-users_roles.database_privileges) — Compare with database-level privileges of the same roles.

## Checklist
- Keep `CREATE` on tablespaces limited to owner or administrative roles.
- Revoke tablespace privileges from `PUBLIC`.
