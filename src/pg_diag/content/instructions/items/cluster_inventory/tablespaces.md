# Tablespaces

This instruction belongs to report item `cluster_inventory.tablespaces`. The item is backed by `cluster.tablespaces` (SQL query).

## What this item shows
- Tablespace names, owners, locations, and size context.
- Storage placement inventory for database objects.
- Non-default storage paths visible to current user.

## What to watch
- Tablespace on unexpected path or storage tier.
- Large tablespace close to full at filesystem level.
- Deprecated or unused tablespace still present.

## Common fault causes
- Object moved to wrong storage.
- Storage migration incomplete.
- Old tablespace left after decommission.

## Automatic evaluation
- This item is informational because size and placement policy are deployment-specific.
- `pg_tablespace_size` reads exact size for each tablespace and may require privileges; tablespace counts are normally small.

## Related report items
- [os.tablespace_directory_permissions](#item-os.tablespace_directory_permissions) — Verify permissions on tablespace directories.
- [os.mounts](#item-os.mounts) — Map tablespaces to backing filesystems.
- [os.disk_encryption_status](#item-os.disk_encryption_status) — Check at-rest encryption evidence for tablespace storage.
- [storage_vacuum.table_size_detailed](#item-storage_vacuum.table_size_detailed) — Identify large relations stored in tablespaces.

## Checklist
- Map tablespace paths to mounted filesystems.
- Confirm backups cover all tablespace locations.
- Review object placement for high-I/O relations.
