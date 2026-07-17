# Privileged Login Roles

This instruction belongs to report item `cluster_inventory.privileged_login_roles`.

This item lists login-enabled roles with cluster-level administrative privileges.

## What this item shows
- Login roles with `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `REPLICATION`, or `BYPASSRLS`.
- Connection limit and risk reason for each role.

## What to watch
- Findings whose severity or evidence differs from the approved cluster security baseline.
- Broad access, weak authentication, sensitive-file exposure, or missing controls that compound other findings.

## Common fault causes
- Package or cloud defaults, legacy compatibility, incomplete hardening, or undocumented operational exceptions.
- A change in one security layer without corresponding role, HBA, filesystem, or extension controls.

## Automatic evaluation

- `medium`: a login role is superuser, can create roles, or bypasses RLS.
- `unknown`: CREATEDB or REPLICATION alone requires comparison with the approved role baseline.
- A standard administrative login is not automatically a `high` finding; remote reachability is checked separately.

## Related report items
- [cluster_inventory.privileged_roles](#item-cluster_inventory.privileged_roles) — Review the complete privileged-role population.
- [cluster_inventory.remote_superuser_access](#item-cluster_inventory.remote_superuser_access) — Check whether privileged logins are reachable remotely.
- [activity_locks.connection_pressure](#item-activity_locks.connection_pressure) — Assess operational impact of privileged login connections.

## Checklist
- Keep superuser and high-privilege roles non-login where possible.
- Use separate application roles without administrative attributes.
- Review each privileged login role owner and lifecycle.
