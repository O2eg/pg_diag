# Backup Repository Permissions

This instruction belongs to `os.backup_repository_permissions`, backed by local Python source `security.backup_repository_permissions`.

## What this item shows
- Existing common backup directories such as pgBackRest and local backup paths.
- Modes that expose recoverable database contents.

## What to watch
- World-readable/writable repository paths or group write access outside the approved backup operator group.

## Automatic evaluation
- World exposure is `high`; other broad permissions are `medium`.
- No discovered standard path is `unsupported`, because custom, remote, container, and object-storage repositories cannot be inferred from absence.

## Common fault causes
- Backup software installed under a custom prefix, repository mounted only during jobs, permissive umask, or wrong backup-agent group ownership.

## Checklist
- Keep backup repositories readable only by trusted backup operators.
- Remove world access from backup trees.
- Verify off-host repository permissions separately.
