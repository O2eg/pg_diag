# Replication Slots

This instruction belongs to report item `replication.replication_slots`. The item is backed by `replication.slots` (SQL query).

## What this item shows
- Cluster-wide physical and logical slots, activity/PID, restart and confirmed-flush LSNs, retained WAL bytes, and xmin horizons.
- Version-dependent slot state exposed safely through optional fields such as `wal_status`, `safe_wal_size_bytes`, invalidation, failover, synchronization, and conflict state.
- Retained bytes relative to the local write LSN on a primary or replay LSN on a standby.

## What to watch
- `wal_status = lost`, an invalidation reason, an inactive slot with growing retained bytes, or an old xmin/catalog xmin.
- A small `safe_wal_size_bytes` when `max_slot_wal_keep_size` limits retention.
- Slot ownership and consumer identity before any destructive action.

## Automatic evaluation
- `high`: PostgreSQL reports that required WAL is lost or the slot is invalidated.
- Inactivity, retained size, and xmin age remain contextual and do not assign severity by themselves.

## Common fault causes
- Abandoned replica, stopped logical consumer, disabled subscription, network outage, or insufficient slot WAL retention.
- Long or prepared transactions in logical decoding.
- Promotion/failover state and version-specific slot synchronization behavior.

## Checklist
- Compare retained bytes with free space and `max_slot_wal_keep_size`.
- Confirm the owning replica, subscription, CDC connector, or backup process.
- Rebuild or drop a slot only through that consumer's documented recovery workflow.
- Empty means the cluster has no replication slots; it is not an error.
