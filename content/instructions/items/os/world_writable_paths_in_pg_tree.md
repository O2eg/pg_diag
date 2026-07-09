# World-Writable Paths In PostgreSQL Trees

This item scans PostgreSQL-sensitive paths for world-writable files or directories.

## What this item shows
- Findings under PGDATA, log directories, tablespaces, and inferred archive paths.
- Path, root, file mode, and risk reason.

## Checklist
- Remove world-write permissions immediately.
- Verify ownership and group policy for the affected tree.
- Check whether untrusted users could replace files before remediation.
