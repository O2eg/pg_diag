# RLS Table Privilege Mismatch

This item lists RLS-enabled tables with broad, grantable, or direct login-role table privileges.

## What this item shows
- RLS table, owner, grantee, privilege, and grant option flag.
- Whether `FORCE ROW LEVEL SECURITY` is enabled.

## Automatic evaluation
- `medium`: access is PUBLIC or can be granted onward.
- `unknown`: a login role has a direct grant; RLS policy evaluation still applies and the access baseline decides whether this is drift.
- Results are bounded to 1000 grants.

## Checklist
- Verify policies cover every role with table access.
- Avoid PUBLIC grants on RLS-protected tables.
- Use group roles and keep grant option tightly limited.
