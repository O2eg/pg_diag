# Cryptographic Extensions

This instruction belongs to report item `cluster_inventory.cryptographic_extensions`.

This item reports missing cryptographic extension support in the connected database.

## What this item shows
- Availability of `pgcrypto` and `pgsodium`.
- Installed version in the connected database.
- Risk level when no cryptographic extension is available or installed.

## What to watch
- Findings whose severity or evidence differs from the approved cluster security baseline.
- Broad access, weak authentication, sensitive-file exposure, or missing controls that compound other findings.

## Common fault causes
- Package or cloud defaults, legacy compatibility, incomplete hardening, or undocumented operational exceptions.
- A change in one security layer without corresponding role, HBA, filesystem, or extension controls.

## Automatic evaluation

- Severity is `unknown`: database-side cryptography is not universally required and may live in the application or KMS.
- Install an extension only for a defined database-side requirement; absence is not a vulnerability.

## Related report items
- [cluster_inventory.extensions](#item-cluster_inventory.extensions) — Review installation and availability details.
- [overview.tls_server_configuration](#item-overview.tls_server_configuration) — Compare database cryptographic support with transport security.
- [cluster_inventory.installed_risky_extensions](#item-cluster_inventory.installed_risky_extensions) — Check capability and risk of installed extensions.

## Checklist
- Install `pgcrypto` or `pgsodium` where database-side hashing or encryption is required.
- Prefer explicit per-database extension installation over assuming package availability.
- Remember that these extensions do not replace filesystem or volume encryption.
