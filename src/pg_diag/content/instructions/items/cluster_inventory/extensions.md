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

## Automatic evaluation
- This is an availability and installation inventory; no extension is automatically required or unsafe here.
- `installed_version` is scoped to the connected database, while `default_version` describes server availability.

## Related report items
- [cluster_inventory.installed_risky_extensions](#item-cluster_inventory.installed_risky_extensions) — Review installed extensions with elevated capabilities.
- [cluster_inventory.cryptographic_extensions](#item-cluster_inventory.cryptographic_extensions) — Check available cryptographic support.
- [cluster_inventory.anonymization_extensions](#item-cluster_inventory.anonymization_extensions) — Check masking and anonymization support.
- [os.extension_directory_permissions](#item-os.extension_directory_permissions) — Verify protection of extension binaries.

## Checklist
- Compare with approved extension inventory.
- Review extension release notes before update.
- Check dependencies before dropping or upgrading extensions.
