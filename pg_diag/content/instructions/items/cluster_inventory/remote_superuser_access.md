## What this item shows

This item checks whether `pg_hba.conf` contains `host*` rules that allow PostgreSQL superusers to connect through network authentication.

The check reads the `hba_file` setting from PostgreSQL, parses the local `pg_hba.conf` file, follows `include`, `include_if_exists`, and `include_dir` directives, expands `@` user files, and evaluates direct superuser names, `all`, and `+role` membership.

## Automatic evaluation
- `high`: a matching login superuser uses trust, or a non-loopback rule is reachable according to `listen_addresses`.
- `medium`: a loopback/samehost host rule matches a login superuser.
- Includes and netmask notation are parsed, but rows are potential matches: PostgreSQL first-match ordering can shadow a later rule.

## Checklist

- Treat any `high` severity result as a security finding.
- Remove superusers from `host`, `hostssl`, `hostnossl`, `hostgssenc`, and `hostnogssenc` rules.
- Prefer local Unix socket access with `peer` authentication for superusers.
- Use non-superuser roles for remote administration and controlled privilege escalation.
- Reload PostgreSQL configuration after changing `pg_hba.conf`.
