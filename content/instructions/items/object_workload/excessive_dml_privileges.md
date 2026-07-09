# Excessive DML Privileges

This item lists PUBLIC or grantable DML privileges on non-system tables in the connected database.

## What this item shows
- `INSERT`, `UPDATE`, `DELETE`, or `TRUNCATE` granted to `PUBLIC`.
- DML privileges that can be granted onward.
- Table owner and grantee context for each finding.

## Checklist
- Revoke DML privileges from `PUBLIC` unless explicitly required.
- Avoid grantable DML privileges for application roles.
- Confirm each listed grant has a current business owner and purpose.
