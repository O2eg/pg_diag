# Cluster Progress

This instruction belongs to report item `maintenance_progress.cluster_progress`. The item is backed by `progress.cluster` (SQL query).

## What this item shows
- Live progress for CLUSTER and VACUUM FULL operations.
- Rewrite or scan phase and relation progress.
- Whether a table rewrite operation is currently active.

## What to watch
- Long-running rewrite.
- Exclusive lock impact on application table.
- Disk usage growing during rewrite.

## Common fault causes
- Manual CLUSTER/VACUUM FULL on large relation.
- Slow storage.
- Insufficient free disk space.
- Maintenance started during traffic.

## Checklist
- Verify lock impact before allowing it to continue.
- Check free disk space.
- Coordinate with application owners for blocking rewrites.
