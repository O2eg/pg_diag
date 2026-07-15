# Sequence Privileges

This item reports PUBLIC or grantable privileges on user-defined sequences.

## What this item shows
- Sequence privileges granted to `PUBLIC`.
- Grantable sequence privileges held by non-owner roles.
- Higher risk for `USAGE` or `UPDATE` grants to `PUBLIC`.

## Automatic evaluation
- `high`: PUBLIC can use or advance a user sequence.
- `medium`: another sequence privilege is PUBLIC or can be granted onward.
- Ordinary explicit non-grantable role access is not included.

## Checklist
- Revoke unnecessary sequence privileges from `PUBLIC`.
- Grant sequence access only to roles that need to read or advance sequence values.
- Review sequence privileges together with table DML privileges.
