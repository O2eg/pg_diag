# Function Execute Privileges

This item reports PUBLIC or grantable `EXECUTE` privileges on user-defined functions.

## What this item shows
- Functions executable by `PUBLIC`.
- Grantable `EXECUTE` privileges held by non-owner roles.
- Higher risk when PUBLIC can execute a `SECURITY DEFINER` function.

## Checklist
- Revoke default PUBLIC function execution where it is not required.
- Keep `SECURITY DEFINER` functions callable only by explicit trusted roles.
- Review function grants after migrations and extension changes.
