# Logical Replication Subscription Workers

This instruction belongs to report item `replication.subscription_workers`. The item is backed by `replication.subscription_workers` (SQL query).

## What this item shows
- Current-database main apply, table synchronization, and version-dependent parallel apply workers from `pg_stat_subscription`.
- Subscription enabled state, worker PIDs, relation, textual receive/end LSNs, message ages, and publisher-receive byte gap.
- PostgreSQL 15+ cumulative apply/sync errors; PostgreSQL 18 conflict totals when exposed by `pg_stat_subscription_stats`.

## What to watch
- An enabled main worker shown as `not running`, stale message times, growing receive gap, or error counters increasing.
- Table synchronization workers that remain on the same relation across captures.
- Worker capacity, subscriber logs, and publisher connectivity.

## Automatic evaluation
- `medium`: an enabled main apply worker is not running, or cumulative apply/sync/conflict counters are non-zero.
- A disabled subscription and normal transient worker turnover do not assign severity.
- PostgreSQL 14 has no subscription error-statistics view, so those fields are null rather than zero.

## Common fault causes
- Publisher connectivity/authentication failure, schema or constraint conflict, disabled subscription, worker limit exhaustion, or apply error.
- Initial table copy, parallel apply lifecycle, or an idle publisher.

## Related report items
- [snapshot_delta_workload.subscription_errors_conflicts_delta](#item-snapshot_delta_workload.subscription_errors_conflicts_delta) — Measure subscription errors and conflicts in the window.
- [snapshot_delta_workload.logical_decoding_slot_delta](#item-snapshot_delta_workload.logical_decoding_slot_delta) — Check related logical-slot progress.
- [replication.replication_slots](#item-replication.replication_slots) — Inspect current slot retention.

## Checklist
- Check subscriber logs and `pg_subscription.subenabled`, then compare error counters with their reset timestamp.
- Treat `publisher_receive_lag_bytes` only as publisher-end versus received WAL; PostgreSQL does not expose the applied LSN here.
- Compare at least two captures before calling a worker stalled.
- Empty means the current database has no subscription rows.
