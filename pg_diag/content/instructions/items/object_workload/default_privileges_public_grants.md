# Default Privileges Public Grants

This item reports `ALTER DEFAULT PRIVILEGES` entries that grant future-object privileges to `PUBLIC` or allow onward grants.

## What this item shows
- Owner, schema scope, and object type affected by default privileges.
- Future-object privileges granted to `PUBLIC`.
- Grantable default privileges held by non-owner roles.

## Automatic evaluation
- `high`: future object privileges are granted to PUBLIC.
- `medium`: a non-owner can grant a default privilege onward.
- The check applies only to explicit default-privilege entries, not existing object ACLs.

## Checklist
- Revoke default PUBLIC grants that are not explicitly required.
- Keep future-object privileges scoped to application and migration roles.
- Review default privileges after schema ownership or deployment changes.
