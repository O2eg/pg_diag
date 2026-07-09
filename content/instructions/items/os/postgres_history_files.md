# PostgreSQL History Files

This item checks local psql history files.

## What this item shows
- History file paths.
- Broad file permissions.
- Lines that appear to contain sensitive SQL or secret-related commands.

## Checklist
- Protect history files with owner-only permissions.
- Disable or scrub history for privileged maintenance sessions.
- Rotate credentials if secrets were typed into psql.
