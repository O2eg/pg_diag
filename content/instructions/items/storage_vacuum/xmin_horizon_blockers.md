# Xmin Horizon Blockers

This instruction belongs to report item `storage_vacuum.xmin_horizon_blockers`. The item is backed by `vacuum.xmin_horizon_blockers` (SQL query).

## What this item shows
- Top blocker per xmin horizon component.
- PID, slot, standby, or prepared transaction responsible for oldest horizon.
- Actionable owner for cleanup-blocking xmin retention.

## What to watch
- One blocker much older than others.
- Application backend holding xmin for long period.
- Replication slot or prepared xact as blocker.

## Common fault causes
- Idle or long transaction.
- Abandoned logical slot.
- Lagging standby feedback.
- Forgotten prepared transaction.

## Checklist
- Resolve blocker type-specific cause.
- Terminate backend only after owner review.
- Drop or advance slots only when consumer ownership is confirmed.
