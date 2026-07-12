# Subscription Errors And Conflicts Delta

This instruction belongs to report item `snapshot_delta_workload.subscription_errors_conflicts_delta`.

## What this item shows
- Apply errors, synchronization errors, and supported logical-replication conflict counters per subscription.

## What to watch
- Any new error or conflict and repeated failures for the same subscription.

## Automatic evaluation
- Any increase in apply errors, synchronization errors, or available conflict counters produces `medium` severity.

## Interval coverage
- Available on PostgreSQL 15 and newer and scoped to the connected database.
- Values require matching subscription OID and unchanged subscription statistics reset time.
- PostgreSQL 15-17 expose apply and synchronization errors but not conflict counters; the conflict Delta is `Unsupported`, never a fabricated zero.

## Common fault causes
- Constraint violations, missing rows, permissions, row-level security, schema drift, and worker failures.

## Checklist
- Inspect subscriber logs and the subscription worker item.
- Correct the underlying data or schema conflict before restarting or skipping work.
