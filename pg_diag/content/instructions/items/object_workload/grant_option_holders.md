# Grant Option Holders

This item lists non-owner roles that can re-grant object privileges.

## What this item shows
- Object, owner, grantee, privilege, and whether the grantee can login.
- Schema, relation, sequence, and function privileges with grant option.

## Automatic evaluation
- `medium` is raised for non-owner grant options because they expand who can delegate access.
- Owner and approved administration roles may be intentional exceptions.
- Results are bounded to 1000 grants.

## Checklist
- Keep `WITH GRANT OPTION` limited to owner or controlled administration roles.
- Review login roles with grant option first.
- Revoke unintended grant option privileges.
