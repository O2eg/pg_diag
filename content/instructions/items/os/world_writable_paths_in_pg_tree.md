# World-Writable Paths In PostgreSQL Trees

This instruction belongs to `os.world_writable_paths_in_pg_tree`, backed by local Python source `security.world_writable_paths_in_pg_tree`.

## What this item shows
- Findings under PGDATA, log directories, tablespaces, and inferred archive paths.
- Path, root, file mode, and risk reason.

## What to watch
- Any world-writable directory or file that can influence database files, logs, tablespaces, or archive handling.

## Automatic evaluation
- Every world-writable path is `high`.
- Scans are bounded to depth 4, 50,000 entries and 100 findings per root. Missing roots, permission errors, or a reached limit produce `unknown` coverage rather than pass.

## Common fault causes
- Recursive chmod, shared application directories, permissive archive targets, temporary troubleshooting changes, or inherited mount ACLs.

## Checklist
- Remove world-write permissions immediately.
- Verify ownership and group policy for the affected tree.
- Check whether untrusted users could replace files before remediation.
