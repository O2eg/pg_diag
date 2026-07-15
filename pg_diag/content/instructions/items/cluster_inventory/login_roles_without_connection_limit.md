# Login Roles Without Connection Limit

This item reports login roles with unlimited per-role connection count.

## What this item shows
- Login roles where `rolconnlimit = -1`.
- Administrative privilege flags for context.
- Risk level for unlimited connection fan-out.

## Automatic evaluation
- Severity is `unknown`: PostgreSQL's default is no per-role limit, and connection pools or global limits may provide the intended control.
- Treat the row as capacity/governance evidence rather than a vulnerability.

## Checklist
- Set per-role connection limits for application and automation users.
- Keep superuser and maintenance roles separate from high-volume application traffic.
- Coordinate role limits with pooler and application connection settings.
