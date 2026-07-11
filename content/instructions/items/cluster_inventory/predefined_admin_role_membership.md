# Predefined Admin Role Membership

This item lists non-superuser, non-system roles that inherit powerful PostgreSQL predefined roles.

## What this item shows
- Membership in roles such as `pg_read_server_files`, `pg_write_server_files`, `pg_execute_server_program`, `pg_read_all_data`, and `pg_write_all_data`.
- Whether the member role can log in.
- Direct or inherited grant depth.

## Automatic evaluation
- `high`: inherited capabilities include server-program execution, server-file write, all-data write, or subscription creation.
- `medium`: read-all, backend signaling, checkpoint, maintenance, monitoring, or related administrative capabilities.
- Findings exclude superusers because their authority already subsumes these roles.

## Checklist
- Review file-access and all-data roles as high-impact privileges.
- Remove inherited admin roles from application users.
- Prefer narrowly scoped operational roles and audited escalation.
