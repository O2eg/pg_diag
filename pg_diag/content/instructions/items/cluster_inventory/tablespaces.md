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

## Checklist
- Map tablespace paths to mounted filesystems.
- Confirm backups cover all tablespace locations.
- Review object placement for high-I/O relations.
