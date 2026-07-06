# Recovery Prefetch

This instruction belongs to report item `replication.recovery_prefetch`. The item is backed by `replication.recovery_prefetch` (SQL query).

## What this item shows
- Recovery prefetch statistics on standby servers that support it.
- Blocks prefetched, hit/miss/skipped counts, and skip reasons.
- Whether WAL replay prefetch is helping standby recovery.

## What to watch
- Many skipped prefetches.
- Prefetch misses high relative to hits.
- No data on versions or roles where prefetch is unavailable.

## Common fault causes
- Standby workload pattern not suitable for prefetch.
- I/O constraints.
- Feature disabled or unsupported version.

## Checklist
- Interpret only on standby/recovery contexts.
- Compare with replay lag and disk reads.
- Check recovery_prefetch setting and PostgreSQL version support.
