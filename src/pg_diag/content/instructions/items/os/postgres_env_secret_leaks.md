# PostgreSQL Environment Secret Leaks

This instruction belongs to report item `os.postgres_env_secret_leaks`.
It is backed by local Python source `security.postgres_env_secret_leaks`.

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

## Related report items
- [cluster_inventory.postgres_client_secret_files](#item-cluster_inventory.postgres_client_secret_files) — Check persistent PostgreSQL credential files.
- [os.postgres_history_files](#item-os.postgres_history_files) — Inspect shell and client history for leaked secrets.
- [os.postgres_service_hardening](#item-os.postgres_service_hardening) — Review service-environment restrictions.

## Checklist
- Avoid long-lived `PGPASSWORD` environment variables.
- Prefer protected service files, peer auth, or secret managers.
- Restart affected processes after rotating exposed credentials.
