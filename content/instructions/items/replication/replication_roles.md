# Replication Roles

This item reports roles with the `REPLICATION` privilege.

## What this item shows
- Roles that can initiate replication.
- Whether replication roles also have superuser, role-admin, database-admin, or bypass-RLS privileges.
- Whether the role can log in directly.

## Checklist
- Keep replication roles dedicated to replication only.
- Avoid combining `REPLICATION` with `SUPERUSER`, `CREATEROLE`, or `BYPASSRLS`.
- Use narrow `pg_hba.conf` rules for replication connections.
