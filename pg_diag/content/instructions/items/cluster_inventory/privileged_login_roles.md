# Privileged Login Roles

This item lists login-enabled roles with cluster-level administrative privileges.

## What this item shows
- Login roles with `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `REPLICATION`, or `BYPASSRLS`.
- Connection limit and risk reason for each role.

## Automatic evaluation
- `medium`: a login role is superuser, can create roles, or bypasses RLS.
- `unknown`: CREATEDB or REPLICATION alone requires comparison with the approved role baseline.
- A standard administrative login is not automatically a `high` finding; remote reachability is checked separately.

## Checklist
- Keep superuser and high-privilege roles non-login where possible.
- Use separate application roles without administrative attributes.
- Review each privileged login role owner and lifecycle.
