# Backup Repository Permissions

This item checks common PostgreSQL backup repository paths.

## What this item shows
- Existing common backup directories such as pgBackRest and local backup paths.
- Modes that expose recoverable database contents.

## Checklist
- Keep backup repositories readable only by trusted backup operators.
- Remove world access from backup trees.
- Verify off-host repository permissions separately.
