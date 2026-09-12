# World-Writable Paths In PostgreSQL Trees

This instruction belongs to report item `os.world_writable_paths_in_pg_tree`.
It is backed by local Python source `security.world_writable_paths_in_pg_tree`.

## What this item shows
- Findings under PGDATA, log directories, tablespaces, and inferred archive paths.
- Path, root, file mode, and risk reason.

## What to watch
- Any world-writable directory or file that can influence database files, logs, tablespaces, or archive handling.

## Automatic evaluation
- Every world-writable path is `high`.
- Scans are bounded to depth 4, 50,000 entries and 100 findings per root. Missing roots, permission errors, or a reached limit produce `unknown` coverage rather than pass.
- Symlinks, sockets and FIFOs are not findings: `find` reports the mode of the link itself (always 0777) and sockets are created world-writable by design; the symlink item reviews link targets and `cluster_inventory.unix_socket_permissions` covers PostgreSQL sockets.
- A sticky directory (`1777`, the `/tmp` layout) is not reported: other users cannot modify or remove entries they do not own.

## Common fault causes
- Recursive chmod, shared application directories, permissive archive targets, temporary troubleshooting changes, or inherited mount ACLs.

## Related report items
- [os.symlinks_in_sensitive_paths](#item-os.symlinks_in_sensitive_paths) — Check whether symlinks redirect trusted paths.
- [cluster_inventory.pgdata_permissions](#item-cluster_inventory.pgdata_permissions) — Review the root data-directory mode.
- [os.postgres_config_file_permissions](#item-os.postgres_config_file_permissions) — Inspect sensitive configuration files under writable paths.

## Checklist
- Remove world-write permissions immediately.
- Verify ownership and group policy for the affected tree.
- Check whether untrusted users could replace files before remediation.
