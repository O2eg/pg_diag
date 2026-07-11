# pg_hba Generic Database Or User

This item lists `pg_hba.conf` rules that use `all` for database or user matching.

## What this item shows
- Generic database field.
- Generic user field.
- Combined broad matching such as `all all`.

## Automatic evaluation
- Severity is `unknown`: `all` is a matching primitive, not a vulnerability by itself.
- Review first-match order, address range, transport type, and authentication method together.

## Checklist
- Prefer explicit databases and roles in access rules.
- Reserve `all` only for intentionally broad low-risk rules.
- Review generic rules together with network range and auth method checks.
