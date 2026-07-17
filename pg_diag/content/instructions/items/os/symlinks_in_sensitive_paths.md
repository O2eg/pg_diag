# Symlinks In Sensitive Paths

This instruction belongs to report item `os.symlinks_in_sensitive_paths`.
It is backed by local Python source `security.symlinks_in_sensitive_paths`.

## What this item shows
- Symlink path, root path, and target.
- PGDATA, log directories, tablespaces, and archive paths are considered.

## What to watch
- Links escaping an expected root, pointing to writable targets, or introduced without change control.

## Automatic evaluation
- Every discovered symlink is `medium` for manual review; intentional tablespace/log layouts can be legitimate.
- Scans are bounded to depth 2, 50,000 entries and 100 findings per root. Unreadable or truncated roots produce `unknown` coverage.

## Common fault causes
- Storage migration, package layout, tablespace indirection, log relocation, or a malicious/wrongly owned replacement target.

## Related report items
- [os.world_writable_paths_in_pg_tree](#item-os.world_writable_paths_in_pg_tree) — Check write access along symlink targets.
- [os.postgres_config_file_permissions](#item-os.postgres_config_file_permissions) — Review configuration paths reached through symlinks.
- [cluster_inventory.pgdata_permissions](#item-cluster_inventory.pgdata_permissions) — Check the containing data-directory permissions.

## Checklist
- Confirm each symlink is intentional.
- Verify target ownership and permissions.
- Pay special attention to links that leave the expected filesystem tree.
