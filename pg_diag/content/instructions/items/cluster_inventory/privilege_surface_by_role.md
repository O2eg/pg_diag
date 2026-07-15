# Privilege Surface By Role

This item summarizes explicit object privileges by grantee role.

## What this item shows
- Explicit privilege count per role.
- Counts by schema, relation, sequence, and function.
- Grant option count and privilege type list.

## Automatic evaluation
- `medium`: the grantee is PUBLIC or at least one explicit privilege is grantable onward.
- `unknown`: all other counts require comparison with the intended access-control baseline.
- Counts cover explicit ACL entries in the connected database, not effective inherited privileges.

## Checklist
- Sort by privilege count to find broad roles.
- Review PUBLIC and login-role footprints first.
- Reduce direct object grants through group roles.
