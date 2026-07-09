# WAL Archive Directory Permissions

This item checks filesystem permissions for paths inferred from `archive_command`.

## What this item shows
- Archive destination paths parsed from the command.
- Directory modes that expose or allow modification of archived WAL.

## Checklist
- Keep WAL archive directories restricted to PostgreSQL and backup automation.
- Avoid world-readable or writable archive paths.
- Verify command parsing manually for complex archive scripts.
