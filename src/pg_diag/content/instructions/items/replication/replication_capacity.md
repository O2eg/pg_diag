# Replication Capacity

This instruction belongs to report item `replication.replication_capacity`. The item is backed by `replication.capacity` (SQL query).

## What this item shows
- One row per replication resource with its limit, current usage, remaining capacity, and utilization: WAL senders (`max_wal_senders`), replication slots (`max_replication_slots`), replication origins (`max_replication_slots`, or `max_active_replication_origins` on PostgreSQL 18 and newer; the limit applies to tracked origins, which only superusers can read from `pg_replication_origin_status`, so usage is the number of running subscription apply and synchronization workers as a lower bound, with the created origin count in `detail`), logical replication workers, synchronization workers per subscription, parallel apply workers per subscription (PostgreSQL 16 and newer), `wal_level`, and `max_slot_wal_keep_size` (PostgreSQL 13 and newer) compared with the largest WAL retained by a slot.
- `wal_keep_size` or `wal_keep_segments` is listed for reference only; it protects standbys without a slot and is independent of slot retention.
- `detail` breaks usage down, for example streaming versus backup senders or active versus inactive slots.

## What to watch
- Senders at the limit: a new standby, `pg_basebackup`, or logical subscriber cannot connect.
- Slots or origins at the limit before a planned subscriber or standby is added.
- `wal_level = replica` with publications defined; subscriptions will fail to decode.
- Slot WAL retention approaching `max_slot_wal_keep_size`; the slot is invalidated when the limit is exceeded.
- Synchronization workers per subscription exhausted during an initial copy of many tables.

## Common fault causes
- Limits left at defaults while standbys, backup jobs, and subscribers were added over time.
- Inactive slots of decommissioned consumers still counting against the limit.
- `wal_level` changed to `replica` after logical replication was set up.

## Automatic evaluation
- `high`: a counted resource is fully used.
- `medium`: usage is at least 90 percent of a counted limit, slot retention is at least 80 percent of `max_slot_wal_keep_size`, or publications exist while `wal_level` is not logical.
- `ok`: all other rows.
- Usage is sampled with bounded catalog reads (10,000 slots, origins, or publications).

## Related report items
- [replication.replication_slots](#item-replication.replication_slots) — Identify the slots and their retained WAL.
- [replication.physical_replication](#item-replication.physical_replication) — See the senders that consume `max_wal_senders`.
- [replication.subscription_workers](#item-replication.subscription_workers) — See the workers that consume logical replication worker slots.
- [cluster_inventory.pending_restart_settings](#item-cluster_inventory.pending_restart_settings) — Most of these limits require a restart to change.

## Checklist
- Keep at least two spare senders and slots for backups and re-synchronization.
- Drop slots of decommissioned consumers.
- Change limits ahead of topology changes because they require a restart.
