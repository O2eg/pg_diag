# Role Password Hashes

This item reports visible login role password hashes weaker than SCRAM-SHA-256.

## What this item shows
- Roles with MD5 or unknown password hash formats.
- Whether affected roles are superusers or can create databases.
- No raw password hash values are included in the report.

## Automatic evaluation
- `high`: a visible login role stores an MD5 verifier.
- `medium`: the visible verifier format is neither SCRAM-SHA-256 nor a recognized SCRAM variant.
- Lack of `pg_shadow` visibility is `unsupported`, not a clean pass; verifier text is never reported.

## Checklist
- Set `password_encryption = 'scram-sha-256'`.
- Reset passwords for roles that still use MD5 hashes.
- Treat unsupported collection as a permissions limitation, not as proof that hashes are safe.
