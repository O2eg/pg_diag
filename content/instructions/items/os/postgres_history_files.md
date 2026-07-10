# PostgreSQL History Files

This instruction belongs to `os.postgres_history_files`, backed by local Python source `security.postgres_history_files`.

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

## Checklist
- Protect history files with owner-only permissions.
- Disable or scrub history for privileged maintenance sessions.
- Rotate credentials if secrets were typed into psql.
