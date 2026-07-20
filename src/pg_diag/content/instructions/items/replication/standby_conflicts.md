# Standby Recovery Conflicts

This instruction belongs to report item `replication.standby_conflicts`. The item is backed by `replication.database_conflicts` (SQL query).

## What this item shows
- Cluster-wide cumulative recovery-conflict counters per database, with server role and the matching database statistics reset time where available.
- Tablespace, lock, snapshot, buffer-pin, and deadlock cancellations; PostgreSQL 18 also includes active logical-slot conflicts.
- On a primary these rows normally remain zero.

## What to watch
- Non-zero counters on a standby, especially increases between captures.
- Snapshot conflicts with long reporting queries and lock conflicts after primary-side DDL.
- Whether mitigation would trade replay freshness, primary bloat, or query availability.

## Automatic evaluation
- `medium`: a database has one or more cumulative recovery conflicts since reset.
- This is historical evidence; it does not prove a conflict is occurring now.

## Common fault causes
- Long standby queries, vacuum cleanup on the primary, DDL replay, buffer pins, or logical-slot invalidation during recovery.
- Low `max_standby_streaming_delay`/`max_standby_archive_delay` or a deliberate no-delay policy.

## Related report items
- [snapshot_delta_workload.standby_recovery_conflicts_delta](#item-snapshot_delta_workload.standby_recovery_conflicts_delta) — Measure conflicts during the capture window.
- [replication.wal_receiver](#item-replication.wal_receiver) — Check standby receive and replay state.
- [storage_vacuum.xmin_horizon_blockers](#item-storage_vacuum.xmin_horizon_blockers) — Look for feedback or horizon conditions affecting cleanup.

## Checklist
- Calculate a delta from two captures and correlate it with canceled-query logs.
- Identify the conflict type before considering delay settings or `hot_standby_feedback`.
- Do not reset shared counters for diagnosis; preserve evidence used by other monitoring.
- Zero rows/counters on a primary do not validate standby behavior elsewhere.
