# Replication Roles

This instruction belongs to report item `replication.replication_roles`. The item is backed by `security.replication_roles` (SQL query).

## What this item shows
- Cluster roles with the `REPLICATION` attribute and their OID, login, connection-limit, superuser, role/database administration, and bypass-RLS attributes.
- Privilege combinations on the role itself; inherited membership and HBA reachability are not expanded by this item.

## What to watch
- Replication combined with superuser or unrelated administrative privileges.
- Login-enabled roles with unexpectedly broad HBA access or credential usage.
- Group roles whose members inherit a broader effective privilege set.

## Automatic evaluation
- `high`: a replication role is also superuser.
- `medium`: it also has `CREATEROLE`, `CREATEDB`, or `BYPASSRLS`.
- A dedicated replication-only role is `ok`; the presence of `REPLICATION` alone is not a vulnerability.
- The bootstrap cluster owner (`OID 10`) is retained as evidence but classified `ok`; its expected superuser capability should be governed through access controls rather than reported as an extra-role finding.

## Common fault causes
- Convenience roles accumulated privileges over time, migration tooling reused an admin account, or membership/HBA rules broadened access.
- Intentional administrative service accounts that require documented compensating controls.

## Checklist
- Trace role membership, ownership, credentials, and matching replication HBA rules before changing attributes.
- Separate privileges only after validating failover, backup, CDC, and subscriber dependencies.
- Empty means no non-system role directly has the `REPLICATION` attribute.
