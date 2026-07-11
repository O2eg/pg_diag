# Function Execute Privileges

This item reports PUBLIC or grantable `EXECUTE` privileges on user-defined functions.

## What this item shows
- Functions executable by `PUBLIC`.
- Grantable `EXECUTE` privileges held by non-owner roles.
- Higher risk when PUBLIC can execute a `SECURITY DEFINER` function.

## Automatic evaluation
- `high`: PUBLIC can execute a `SECURITY DEFINER` function with no local `search_path`.
- `medium`: PUBLIC can execute a configured `SECURITY DEFINER` function, or a non-owner can re-grant EXECUTE.
- PUBLIC EXECUTE on an ordinary function is PostgreSQL's default and is shown as `ok`, not as a vulnerability.

## Checklist
- Revoke default PUBLIC function execution where it is not required.
- Keep `SECURITY DEFINER` functions callable only by explicit trusted roles.
- Review function grants after migrations and extension changes.
