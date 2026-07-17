# pg_hba Generic Database Or User

This instruction belongs to report item `cluster_inventory.pg_hba_generic_database_or_user`.

This item lists `pg_hba.conf` rules that use `all` for database or user matching.

## What this item shows
- Generic database field.
- Generic user field.
- Combined broad matching such as `all all`.

## What to watch
- Findings whose severity or evidence differs from the approved cluster security baseline.
- Broad access, weak authentication, sensitive-file exposure, or missing controls that compound other findings.

## Common fault causes
- Package or cloud defaults, legacy compatibility, incomplete hardening, or undocumented operational exceptions.
- A change in one security layer without corresponding role, HBA, filesystem, or extension controls.

## Automatic evaluation

- Severity is `unknown`: `all` is a matching primitive, not a vulnerability by itself.
- Review first-match order, address range, transport type, and authentication method together.

## Related report items
- [cluster_inventory.pg_hba_broad_network_ranges](#item-cluster_inventory.pg_hba_broad_network_ranges) — Check the source-network breadth of generic rules.
- [cluster_inventory.pg_hba_insecure_auth_methods](#item-cluster_inventory.pg_hba_insecure_auth_methods) — Review authentication strength.
- [cluster_inventory.pg_hba_tls_enforcement](#item-cluster_inventory.pg_hba_tls_enforcement) — Check transport protection.

## Checklist
- Prefer explicit databases and roles in access rules.
- Reserve `all` only for intentionally broad low-risk rules.
- Review generic rules together with network range and auth method checks.
