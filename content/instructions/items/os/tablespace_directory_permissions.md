# Tablespace Directory Permissions

This instruction belongs to `os.tablespace_directory_permissions`, backed by local Python source `security.tablespace_directory_permissions`.

## What this item shows
- Tablespace name and filesystem path.
- Directory mode, owner, group, and risk reason.

## What to watch
- World access, group write access, missing paths, or paths inaccessible to the collector.

## Automatic evaluation
- World read/write exposure is `high`; other broad permissions and unavailable path evidence are `medium`.
- `empty` is valid when there are no user-defined tablespaces or all returned paths pass the mode check.

## Common fault causes
- Tablespace provisioned with a permissive umask, mount ownership drift, failed storage attachment, or collection from a different mount namespace.

## Checklist
- Keep tablespace directories owned by postgres.
- Remove world access and untrusted group write access.
- Review storage mount permissions as well as the directory itself.
