# Log File Permissions

This item checks PostgreSQL log directory and recent log file permissions.

## What this item shows
- Active log directory from PostgreSQL settings.
- Recent files visible in that directory.
- Modes that expose logs to untrusted OS users.

## Checklist
- Keep log directories inaccessible to untrusted users.
- Avoid world-readable PostgreSQL logs.
- Treat logs as sensitive because they may contain SQL, users, and paths.
