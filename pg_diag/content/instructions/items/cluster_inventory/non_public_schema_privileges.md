# Non-Public Schema Privileges

This item reports risky grants on non-system schemas other than `public`.

## What this item shows
- `PUBLIC` privileges on application schemas.
- Non-owner `CREATE` privileges on schemas.
- Grantable schema privileges held by non-owner roles.

## Automatic evaluation
- `high`: PUBLIC can CREATE in a non-system schema.
- `medium`: a non-owner can CREATE or re-grant privileges.
- `unknown`: PUBLIC has only another privilege such as USAGE; compare it with the schema baseline.

## Checklist
- Revoke broad schema privileges from `PUBLIC`.
- Keep schema `CREATE` privileges limited to owners or migration roles.
- Review schema grants after extension installation and migrations.
