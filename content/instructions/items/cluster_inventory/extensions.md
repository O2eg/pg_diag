# Available Extensions

This instruction belongs to report item `cluster_inventory.extensions`. The item is backed by `cluster.extensions` (SQL query).

## What this item shows
- Installed and available PostgreSQL extensions with versions.
- Extension version drift and upgrade context.
- Extension inventory visible to current user.

## What to watch
- Installed version older than default/available version.
- Unexpected extension in production database.
- Required extension missing.

## Common fault causes
- Extension upgrade not run after PostgreSQL upgrade.
- Manual CREATE EXTENSION outside standard process.
- Managed-service extension availability differs by version.

## Checklist
- Compare with approved extension inventory.
- Review extension release notes before update.
- Check dependencies before dropping or upgrading extensions.
