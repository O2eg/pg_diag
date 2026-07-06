# Physical Replication Senders

This instruction belongs to report item `replication.physical_replication`. The item is backed by `replication.physical_replication` (SQL query).

## What this item shows
- Current rows from pg_stat_replication for WAL sender processes.
- Per-standby state, sync state, LSN positions, and lag values where available.
- Whether the primary is actively streaming to physical standbys.

## What to watch
- Standby state not streaming.
- Replay lag or flush lag increasing.
- Unexpected sync_state for synchronous replicas.
- Missing standby rows when replicas are expected.

## Common fault causes
- Network interruption.
- Standby down or slow.
- WAL sender disconnected.
- Synchronous standby misconfiguration.

## Checklist
- Identify lag stage using sent/write/flush/replay positions.
- Check standby logs and receiver state.
- Confirm synchronous_standby_names expectations.
