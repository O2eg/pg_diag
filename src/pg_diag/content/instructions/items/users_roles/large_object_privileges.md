# Large Object Privileges

This instruction belongs to report item `users_roles.large_object_privileges`. The item is backed by `roles.large_object_privileges` (SQL query).

## What this item shows
- Explicit `SELECT` and `UPDATE` privileges on large objects from `pg_largeobject_metadata`, aggregated by owner, grantee, `grantee_kind`, and privilege with `object_count` and `grantable_object_count`.
- The `lo_compat_privileges` setting; when it is `on`, PostgreSQL skips large object privilege checks entirely and the item adds a `[lo_compat_privileges]` finding row.
- Owner entries are omitted; large objects without an explicit ACL produce no rows.

## What to watch
- `lo_compat_privileges = on`, which exposes every large object to every role regardless of grants.
- `PUBLIC` or broad group roles with `UPDATE` on large objects that store documents or binaries.
- Large objects owned by login roles that are scheduled for removal; `DROP ROLE` fails until ownership is reassigned.

## Common fault causes
- Legacy applications migrated from PostgreSQL 8.x with `lo_compat_privileges` left on.
- Large objects created by application users and shared through `PUBLIC` grants.
- Ownership never reassigned after the creating role was replaced.

## Automatic evaluation
- `medium`: `lo_compat_privileges` is on.
- Privilege rows themselves are informational.
- Large objects with an ACL are sampled by OID (10,000), ACL expansion is bounded to 3,000 rows, and the result to 3,000 rows; coverage flags mark partial results and add a `[coverage]` row.

## Related report items
- [users_roles.object_privileges_by_grantee](#item-users_roles.object_privileges_by_grantee) — Compare with privileges on ordinary relations and functions.
- [overview.pg_settings](#item-overview.pg_settings) — Check the `lo_compat_privileges` setting and its source.

## Checklist
- Turn `lo_compat_privileges` off after verifying that applications grant large object access explicitly.
- Grant large object privileges to group roles rather than users or `PUBLIC`.
- Reassign large object ownership before dropping roles.
