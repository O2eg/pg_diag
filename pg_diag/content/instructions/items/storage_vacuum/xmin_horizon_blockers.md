# Xmin Horizon Blockers

This instruction belongs to report item `storage_vacuum.xmin_horizon_blockers`. The item is backed by `vacuum.xmin_horizon_blockers` (SQL query).

## What this item shows
- The oldest visible holder per activity, slot xmin, slot catalog xmin, WAL sender feedback, and prepared-transaction component.
- PID/backend type, identity, query evidence, slot state, standby state, or prepared GID as applicable.

## What to watch
- A rapidly aging holder, inactive/invalidated slot, unexpected backend type, or abandoned prepared transaction.
- Hidden query/user fields under restricted statistics visibility.

## Automatic evaluation
- No automatic severity: this list identifies ownership but age/action thresholds are deployment-specific.

## Common fault causes
- Long transactions, background-worker snapshots, logical decoding, standby feedback, inactive slots, and failed two-phase workflows.

## Checklist
- Verify owner and downstream dependency before intervention.
- Never drop/advance slots or finish prepared transactions solely from this row.
- Empty means none of the represented components exposed an xmin holder.
