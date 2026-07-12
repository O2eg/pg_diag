# SLRU Activity Delta

This instruction belongs to report item `snapshot_delta_workload.slru_activity_delta`.

## What this item shows
- Reads, hits, writes, zeroing, existence checks, flushes, and truncations per PostgreSQL SLRU cache.

## What to watch
- High read volume with relatively few hits and bursts of writes or flushes aligned with database latency.

## Automatic evaluation
- No severity is assigned because SLRU behavior depends on transaction rate and enabled features.

## Interval coverage
- Each SLRU row requires unchanged per-row `stats_reset` and presence at both endpoints.

## Common fault causes
- High transaction or multixact churn, commit timestamp tracking, subtransaction use, and notification traffic.

## Checklist
- Identify the affected SLRU by name and correlate it with transaction workload.
- Compare SLRU writes with checkpointer and OS storage evidence.
