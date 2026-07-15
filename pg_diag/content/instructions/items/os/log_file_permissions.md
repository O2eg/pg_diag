# Log File Permissions

This instruction belongs to `os.log_file_permissions`, backed by local Python source `security.log_file_permissions`.

## What this item shows
- Active log directory from PostgreSQL settings.
- Recent files visible in that directory.
- Modes that expose logs to untrusted OS users.

## What to watch
- World access, group write access, an unreadable directory, or a warning that only the newest 100 files were inspected.

## Automatic evaluation
- Direct world exposure is `high`; other broad permissions and missing path evidence are `medium`.
- Incomplete enumeration produces an explicit coverage warning. With `logging_collector=off`, this filesystem check is `skipped/unknown`; external/journald controls must be reviewed separately.

## Common fault causes
- Permissive `log_file_mode`, logrotate ownership drift, shared log directories, or logs mounted from another namespace.

## Checklist
- Keep log directories inaccessible to untrusted users.
- Avoid world-readable PostgreSQL logs.
- Treat logs as sensitive because they may contain SQL, users, and paths.
