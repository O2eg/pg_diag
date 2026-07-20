# Login Roles Without Connection Limit

This instruction belongs to report item `cluster_inventory.login_roles_without_connection_limit`.

This item reports login roles with unlimited per-role connection count.

## What this item shows
- Login roles where `rolconnlimit = -1`.
- Administrative privilege flags for context.
- Risk level for unlimited connection fan-out.

## What to watch
- Findings whose severity or evidence differs from the approved cluster security baseline.
- Broad access, weak authentication, sensitive-file exposure, or missing controls that compound other findings.

## Common fault causes
- Package or cloud defaults, legacy compatibility, incomplete hardening, or undocumented operational exceptions.
- A change in one security layer without corresponding role, HBA, filesystem, or extension controls.

## Automatic evaluation

- Severity is `unknown`: PostgreSQL's default is no per-role limit, and connection pools or global limits may provide the intended control.
- Treat the row as capacity/governance evidence rather than a vulnerability.

## Related report items
- [activity_locks.connection_pressure](#item-activity_locks.connection_pressure) — Check current cluster connection pressure.
- [snapshot_charts_db.database_backends](#item-snapshot_charts_db.database_backends) — Inspect backend-count trends.
- [cluster_inventory.privileged_login_roles](#item-cluster_inventory.privileged_login_roles) — Prioritize privileged login roles.

## Checklist
- Set per-role connection limits for application and automation users.
- Keep superuser and maintenance roles separate from high-volume application traffic.
- Coordinate role limits with pooler and application connection settings.
