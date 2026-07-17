# Role Password Hashes

This instruction belongs to report item `cluster_inventory.role_password_hashes`.

This item reports visible login role password hashes weaker than SCRAM-SHA-256.

## What this item shows
- Roles with MD5 or unknown password hash formats.
- Whether affected roles are superusers or can create databases.
- No raw password hash values are included in the report.

## What to watch
- Findings whose severity or evidence differs from the approved cluster security baseline.
- Broad access, weak authentication, sensitive-file exposure, or missing controls that compound other findings.

## Common fault causes
- Package or cloud defaults, legacy compatibility, incomplete hardening, or undocumented operational exceptions.
- A change in one security layer without corresponding role, HBA, filesystem, or extension controls.

## Automatic evaluation

- `high`: a visible login role stores an MD5 verifier.
- `medium`: the visible verifier format is neither SCRAM-SHA-256 nor a recognized SCRAM variant.
- Lack of `pg_shadow` visibility is `unsupported`, not a clean pass; verifier text is never reported.

## Related report items
- [overview.password_encryption](#item-overview.password_encryption) — Check the policy for newly created password verifiers.
- [cluster_inventory.pg_hba_insecure_auth_methods](#item-cluster_inventory.pg_hba_insecure_auth_methods) — Review authentication methods accepting these verifiers.
- [cluster_inventory.postgres_client_secret_files](#item-cluster_inventory.postgres_client_secret_files) — Check client-side credential storage.

## Checklist
- Set `password_encryption = 'scram-sha-256'`.
- Reset passwords for roles that still use MD5 hashes.
- Treat unsupported collection as a permissions limitation, not as proof that hashes are safe.
