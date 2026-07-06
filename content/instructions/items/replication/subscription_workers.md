# Logical Replication Subscription Workers

This instruction belongs to report item `replication.subscription_workers`. The item is backed by `replication.subscription_workers` (SQL query).

## What this item shows
- Logical replication subscription worker state.
- Worker PID, relation sync state, LSN progress, and error context where visible.
- Whether logical subscriptions are actively applying changes.

## What to watch
- Worker not running for enabled subscription.
- Apply lag not advancing.
- Relation sync stuck.
- Unexpected disabled subscription.

## Common fault causes
- Subscriber connection failure.
- Schema mismatch.
- Worker limit reached.
- Apply error on subscriber.

## Checklist
- Check subscriber logs for apply errors.
- Confirm subscription enabled state.
- Compare worker LSN with publisher WAL progress.
