# Role Password Hashes

This item reports visible login role password hashes weaker than SCRAM-SHA-256.

## What this item shows
- Roles with MD5 or unknown password hash formats.
- Whether affected roles are superusers or can create databases.
- No raw password hash values are included in the report.

## Checklist
- Set `password_encryption = 'scram-sha-256'`.
- Reset passwords for roles that still use MD5 hashes.
- Treat unsupported collection as a permissions limitation, not as proof that hashes are safe.
