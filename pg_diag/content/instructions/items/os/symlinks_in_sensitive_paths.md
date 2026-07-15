# Symlinks In Sensitive Paths

This instruction belongs to `os.symlinks_in_sensitive_paths`, backed by local Python source `security.symlinks_in_sensitive_paths`.

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

## Checklist
- Confirm each symlink is intentional.
- Verify target ownership and permissions.
- Pay special attention to links that leave the expected filesystem tree.
