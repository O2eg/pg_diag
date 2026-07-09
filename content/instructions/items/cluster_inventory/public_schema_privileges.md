# Public Schema Privileges

This item lists risky grants on schema `public` in the connected database.

## What this item shows
- `PUBLIC CREATE` on schema `public`.
- Non-owner `CREATE` privileges that allow object creation in `public`.
- Grantable non-owner schema privileges.

## Checklist
- Revoke `CREATE` on schema `public` from `PUBLIC`.
- Keep object creation limited to schema owners or migration roles.
- Review grants after application or extension installation.
