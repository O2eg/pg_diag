# WAL Position

This instruction belongs to report item `wal_io_checkpoints.wal_position`. The item is backed by `wal.position` (SQL query).

## What this item shows
- Server role, system identifier, control-file timeline, uptime, and a role-specific current WAL position.
- Primary insert/write/flush LSNs or standby receive/replay LSNs and their byte gap.
- Last replayed transaction timestamp on a standby; primary-only and standby-only fields remain null on the other role.

## What to watch
- Unexpected role/system identifier/timeline, a receive-to-replay gap growing across captures, or positions not advancing during expected activity.
- Timeline changes after promotion or restore.

## Automatic evaluation
- No automatic severity: a static position can be correct for an idle server, and expected role/topology is deployment-specific.

## Common fault causes
- Idle workload, archive-only recovery, paused/delayed replay, wrong instance, promotion, restore, or upstream interruption.

## Checklist
- Compare textual LSNs only within the appropriate timeline and use byte gaps for arithmetic.
- Do not treat `seconds_since_last_replayed_xact` as replay lag when the primary is idle.
- Use repeated captures or WAL growth charts for rates.
- Confirm system identifier and timeline during failover investigations.
