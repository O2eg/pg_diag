# Background Writer

This instruction belongs to report item `wal_io_checkpoints.bgwriter`. The item is backed by `checkpoints.bgwriter` (SQL query).

## What this item shows
- Background writer counters from pg_stat_bgwriter or version-specific equivalent.
- How often background writer cleans buffers and whether it reaches maxwritten_clean.
- Buffer allocation pressure outside checkpoints.

## What to watch
- maxwritten_clean increasing often.
- buffers_alloc high during workload.
- Background writer unable to keep up with dirty buffer churn.

## Common fault causes
- Write-heavy workload.
- shared_buffers churn.
- bgwriter settings too conservative.
- Checkpoint pressure shifting writes.

## Checklist
- Compare with checkpointer and pg_stat_io backend writes.
- Tune bgwriter only after confirming sustained pressure.
- Use snapshots for rate, not cumulative totals alone.
