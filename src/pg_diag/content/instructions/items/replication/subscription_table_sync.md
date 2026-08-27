# Subscription Table Synchronization

This instruction belongs to report item `replication.subscription_table_sync`. The item is backed by `replication.subscription_table_sync` (SQL query).

## What this item shows
- Every table of every logical subscription in the connected database with its synchronization `state` (`initialize`, `data copy`, `finished copy`, `synchronized`, `ready`), the synchronized LSN, and whether a synchronization worker is currently running for it.
- Per-subscription counts of sampled tables, ready tables, and tables that are not ready, plus whether the apply worker is running.
- Names come from `pg_stat_subscription`, so the item works without superuser access on every supported version.

## What to watch
- Tables that stay in `data copy` or `finished copy` for a long time; the copy may be waiting on a lock, a slow publisher, or a free synchronization worker.
- Tables in `initialize` with no worker while the apply worker runs; check `max_sync_workers_per_subscription` and worker errors in the log.
- Tables added on the publisher that never appear here; the subscription needs `ALTER SUBSCRIPTION ... REFRESH PUBLICATION`.

## Common fault causes
- Initial copy of large tables blocked by long transactions or lock waits on the subscriber.
- Unique constraint violations during the copy that restart synchronization repeatedly.
- Subscriber schema differences that stop the copy for one table.

## Automatic evaluation
- `ok`: the table is ready.
- `unknown`: synchronization is in progress with a running worker, or the apply worker is not running.
- `medium`: the table is not ready, no synchronization worker runs for it, and the apply worker is running.
- Up to 3,000 subscription tables are listed, not-ready tables first; `result_truncated` marks partial coverage.

## Related report items
- [replication.subscription_workers](#item-replication.subscription_workers) — Check apply and synchronization worker errors and lag.
- [replication.replication_capacity](#item-replication.replication_capacity) — Verify synchronization worker limits.
- [activity_locks.lock_waits](#item-activity_locks.lock_waits) — Find locks that block the initial copy.

## Checklist
- Refresh the subscription after adding tables to the publication.
- Raise `max_sync_workers_per_subscription` for subscriptions with many large tables.
- Resolve constraint violations reported in the subscriber log before retrying.
