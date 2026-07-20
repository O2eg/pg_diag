# Password Encryption

This instruction belongs to report item `overview.password_encryption`. The item is backed by `security.password_encryption` (SQL query).

## What this item shows
- Current `password_encryption` value.
- Configuration source and pending restart flag.
- Risk level for non-SCRAM password hashing.

## What to watch
- `md5` produces `high`; any other non-SCRAM value produces `medium`.
- An empty result means new passwords created by sessions using this setting default to SCRAM.
- This setting does not prove that existing role password verifiers have been migrated from MD5.

## Common fault causes
- Legacy clients cannot authenticate with SCRAM.
- The cluster setting was changed but existing passwords were never rotated.
- A role or database override changes `password_encryption` for selected sessions.

## Applicability
- The check matters only for roles using PostgreSQL-managed passwords.
- Certificate, GSSAPI, LDAP, PAM, OAuth, and other external authentication paths have different password controls.

## Automatic evaluation
- Returned rows use the `risk_level` described in What to watch. An empty result does not verify existing role password hashes.

## Related report items
- [cluster_inventory.role_password_hashes](#item-cluster_inventory.role_password_hashes) — Verify the hashes already stored for login roles.
- [cluster_inventory.pg_hba_insecure_auth_methods](#item-cluster_inventory.pg_hba_insecure_auth_methods) — Check whether HBA rules still permit weak authentication.

## Checklist
- Set `password_encryption = 'scram-sha-256'`.
- Rotate or reset old MD5 password hashes where possible.
- Verify client SCRAM support before changing authentication rules.
- Apply the setting to new sessions; a PostgreSQL restart is not intrinsically required for this user-context parameter.
