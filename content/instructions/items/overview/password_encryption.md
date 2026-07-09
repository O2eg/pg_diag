# Password Encryption

This item reports `password_encryption` values weaker than `scram-sha-256`.

## What this item shows
- Current `password_encryption` value.
- Configuration source and pending restart flag.
- Risk level for non-SCRAM password hashing.

## Checklist
- Set `password_encryption = 'scram-sha-256'`.
- Rotate or reset old MD5 password hashes where possible.
- Reload or restart PostgreSQL if the setting change requires it.
