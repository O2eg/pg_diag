# PostgreSQL History Files

This instruction belongs to report item `os.postgres_history_files`.
It is backed by local Python source `security.postgres_history_files`.

## What this item shows
- History file paths.
- Broad file permissions.
- Lines that appear to contain sensitive SQL or secret-related commands.

## What to watch
- Broad permissions or history lines matching password, secret, token, and role-management keywords.

## Automatic evaluation
- World-readable history or a sensitive keyword match is `high`; group exposure or unreadable metadata is `medium`.
- Only known home locations and at most the first 1 MiB/20 findings per file are inspected. Keyword matches can be false positives and secret values are not emitted.

## Common fault causes
- `psql` used interactively for privileged work, permissive umask, copied home directories, or credentials pasted into SQL/meta-commands.

## Related report items
- [cluster_inventory.postgres_client_secret_files](#item-cluster_inventory.postgres_client_secret_files) — Check other persistent client secret files.
- [os.postgres_env_secret_leaks](#item-os.postgres_env_secret_leaks) — Check secrets exposed through process environments.

## Checklist
- Protect history files with owner-only permissions.
- Disable or scrub history for privileged maintenance sessions.
- Rotate credentials if secrets were typed into psql.
