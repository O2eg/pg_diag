# WAL Position

This instruction belongs to report item `wal_io_checkpoints.wal_position`. The item is backed by `wal.position` (SQL query).

## What this item shows
- Current WAL insert/flush/replay position and timeline context.
- Whether the server is primary or in recovery.
- LSN baseline for comparing replication and WAL movement.

## What to watch
- Unexpected recovery state.
- WAL position not advancing during expected writes.
- Timeline change after failover.

## Common fault causes
- Idle workload.
- Server connected to wrong instance.
- Failover or restore created new timeline.
- Permissions hiding related replication context.

## Checklist
- Record LSN before and after tests or failover.
- Compare with replication sender/receiver positions.
- Use WAL growth metrics for rate, not this point-in-time value alone.
