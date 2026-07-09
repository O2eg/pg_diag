# Symlinks In Sensitive Paths

This item lists symlinks under PostgreSQL-sensitive top-level paths.

## What this item shows
- Symlink path, root path, and target.
- PGDATA, log directories, tablespaces, and archive paths are considered.

## Checklist
- Confirm each symlink is intentional.
- Verify target ownership and permissions.
- Pay special attention to links that leave the expected filesystem tree.
