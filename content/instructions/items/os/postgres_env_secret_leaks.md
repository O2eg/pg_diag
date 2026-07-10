# PostgreSQL Environment Secret Leaks

This instruction belongs to `os.postgres_env_secret_leaks`, backed by local Python source `security.postgres_env_secret_leaks`.

## What this item shows
- Process id and command line for environments that appear to contain PostgreSQL secrets.
- Secret values are not printed.

## What to watch
- Processes carrying `PGPASSWORD` or a PostgreSQL URI with embedded credentials.

## Automatic evaluation
- A detected credential pattern is `high`.
- A clean `pass` requires all enumerated process environments to be readable. Inaccessible or exited processes produce `unknown` coverage; no readable environment is `unsupported`.

## Common fault causes
- Service environment files, shell exports, CI jobs, connection URLs passed to long-lived agents, or secrets inherited by child processes.

## Checklist
- Avoid long-lived `PGPASSWORD` environment variables.
- Prefer protected service files, peer auth, or secret managers.
- Restart affected processes after rotating exposed credentials.
