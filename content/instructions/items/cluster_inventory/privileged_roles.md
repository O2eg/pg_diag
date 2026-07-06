# Privileged Roles

This instruction belongs to report item `cluster_inventory.privileged_roles`. The item is backed by `cluster.roles_privileges` (SQL query).

## What this item shows
- Roles with superuser, create-db, create-role, replication, bypass-RLS, or similar privileges.
- Security-sensitive role inventory visible to current user.
- Potential privilege sprawl.

## What to watch
- Unexpected superuser or bypassrls role.
- Login-enabled privileged role not tied to service owner.
- Privileged roles unused but still active.

## Common fault causes
- Legacy admin role never removed.
- Migration or support role left behind.
- Privilege granted broadly for troubleshooting.

## Checklist
- Validate each privileged role owner and purpose.
- Remove or restrict unused privileged roles.
- Audit login and membership paths.
