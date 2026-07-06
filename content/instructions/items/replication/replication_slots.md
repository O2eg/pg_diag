# Replication Slots

This instruction belongs to report item `replication.replication_slots`. The item is backed by `replication.slots` (SQL query).

## What this item shows
- Physical and logical replication slots.
- Retained WAL, active state, restart_lsn, confirmed_flush_lsn, and xmin/catalog_xmin impact.
- Slots that can retain WAL or vacuum horizons.

## What to watch
- Inactive slot retaining WAL.
- catalog_xmin or xmin preventing cleanup.
- Slot retained bytes growing quickly.

## Common fault causes
- Abandoned replica or logical consumer.
- Stopped subscription.
- Consumer lag.
- Slot not dropped after migration.

## Checklist
- Confirm slot owner before dropping.
- Compare retained WAL with disk capacity.
- Check logical subscribers and physical standbys.
