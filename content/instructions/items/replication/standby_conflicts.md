# Standby Recovery Conflicts

This instruction belongs to report item `replication.standby_conflicts`. The item is backed by `replication.database_conflicts` (SQL query).

## What this item shows
- Recovery conflict counters for the current standby database.
- Canceled queries caused by replay conflicts such as locks, snapshots, buffers, or tablespace drops.
- Whether read workload on standby conflicts with WAL replay.

## What to watch
- Conflict counters increasing during reporting workload.
- Snapshot conflicts with long standby queries.
- Lock conflicts after DDL on primary.

## Common fault causes
- Long queries on standby.
- Vacuum cleanup on primary.
- DDL replay.
- hot_standby_feedback policy tradeoff.

## Checklist
- Use deltas or repeated captures to see current conflict rate.
- Identify standby queries being canceled.
- Balance replay freshness against long-running standby reads.
