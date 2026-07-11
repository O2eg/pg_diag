# Excessive DML Privileges

This item lists PUBLIC or grantable DML privileges on non-system tables in the connected database.

## What this item shows
- `INSERT`, `UPDATE`, `DELETE`, or `TRUNCATE` granted to `PUBLIC`.
- DML privileges that can be granted onward.
- Table owner and grantee context for each finding.

## Automatic evaluation
- `high`: PUBLIC has a write privilege on a user table.
- `medium`: a non-owner can grant DML privileges onward.
- Review inherited role membership separately; this item evaluates object ACL entries.
- ACLs are read from PostgreSQL catalogs for all user relations in the connected database, rather than the current role's information-schema visibility subset.

## Checklist
- Revoke DML privileges from `PUBLIC` unless explicitly required.
- Avoid grantable DML privileges for application roles.
- Confirm each listed grant has a current business owner and purpose.
