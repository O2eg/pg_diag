# Tablespace Directory Permissions

This item checks local permissions for PostgreSQL tablespace directories.

## What this item shows
- Tablespace name and filesystem path.
- Directory mode, owner, group, and risk reason.

## Checklist
- Keep tablespace directories owned by postgres.
- Remove world access and untrusted group write access.
- Review storage mount permissions as well as the directory itself.
