# Privileged Login Roles

This item lists login-enabled roles with cluster-level administrative privileges.

## What this item shows
- Login roles with `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `REPLICATION`, or `BYPASSRLS`.
- Connection limit and risk reason for each role.

## Checklist
- Keep superuser and high-privilege roles non-login where possible.
- Use separate application roles without administrative attributes.
- Review each privileged login role owner and lifecycle.
