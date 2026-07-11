# Direct User Grants

This item lists object privileges granted directly to login roles.

## What this item shows
- Object, owner, grantee login role, privilege, and grant option flag.
- Schema, relation, sequence, and function grants.

## Automatic evaluation
- Severity is `unknown`: direct grants are a governance-policy question, not a PostgreSQL correctness failure.
- Results are bounded to 1000 grants and must be compared with the role-management baseline.

## Checklist
- Prefer grants to group roles instead of individual login users.
- Move one-off direct grants into auditable role membership.
- Revoke direct grants that no longer match operational needs.
