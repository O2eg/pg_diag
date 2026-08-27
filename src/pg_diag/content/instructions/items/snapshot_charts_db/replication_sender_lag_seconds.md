# Replication Sender Lag Seconds

This instruction belongs to report item `snapshot_charts_db.replication_sender_lag_seconds`. The item is backed by `replication.sender_lag_seconds` (metric over `metrics.replication_sender_lag_seconds`).

## What this item shows
- For every WAL sender observed during the snapshot window: `write_lag`, `flush_lag`, and `replay_lag` from `pg_stat_replication` at every sample, in seconds.
- Time lag is the delay between WAL flushed on the primary and the standby's write, flush, and replay confirmations; it is the value synchronous commits wait for.

## What to watch
- `flush_lag` on synchronous standbys: it is the commit latency added by `synchronous_commit = on`.
- `replay_lag` on read replicas: it is the staleness visible to read traffic.
- Empty stretches: PostgreSQL reports time lag only while the standby keeps confirming; an idle primary shows gaps rather than zero.

## Common fault causes
- Network latency or packet loss between primary and standby.
- Standby disks with slow `fsync`.
- Recovery conflicts or heavy standby queries slowing replay.

## Automatic evaluation
- Charts are informational and assign no severity.
- Up to 50 senders are sampled per snapshot.

## Related report items
- [snapshot_charts_db.replication_sender_lag_bytes](#item-snapshot_charts_db.replication_sender_lag_bytes) — Compare time lag with byte lag.
- [replication.synchronous_replication_status](#item-replication.synchronous_replication_status) — Check which senders are synchronous.

## Checklist
- Compare flush lag with the application's commit latency expectations.
- Investigate replay lag on read replicas before changing standby settings.
