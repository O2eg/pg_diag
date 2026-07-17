# pg_hba Insecure Auth Methods

This instruction belongs to report item `cluster_inventory.pg_hba_insecure_auth_methods`.

This item lists `pg_hba.conf` rules that use insecure authentication methods.

## What this item shows
- `trust`, `password`, `ident`, and `md5` authentication rules.
- File path, line number, connection type, database, user, address, and raw rule text.

## What to watch
- Findings whose severity or evidence differs from the approved cluster security baseline.
- Broad access, weak authentication, sensitive-file exposure, or missing controls that compound other findings.

## Common fault causes
- Package or cloud defaults, legacy compatibility, incomplete hardening, or undocumented operational exceptions.
- A change in one security layer without corresponding role, HBA, filesystem, or extension controls.

## Automatic evaluation

- `high`: `trust` permits authentication without a password.
- `medium`: `password`, `ident`, or `md5` requires review; an `md5` rule can negotiate SCRAM when the stored verifier is SCRAM.
- Rule order and transport encryption must be considered before remediation.

## Related report items
- [cluster_inventory.role_password_hashes](#item-cluster_inventory.role_password_hashes) — Review password verifiers used by login roles.
- [overview.password_encryption](#item-overview.password_encryption) — Check the password hashing policy.
- [cluster_inventory.pg_hba_tls_enforcement](#item-cluster_inventory.pg_hba_tls_enforcement) — Determine whether weak authentication is also unencrypted.

## Checklist
- Replace `trust` with `peer` for local administration or strong authentication for network access.
- Prefer `scram-sha-256` over `md5`.
- Avoid `password` and `ident` for host rules.
