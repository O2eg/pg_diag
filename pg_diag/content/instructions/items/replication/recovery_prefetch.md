# Recovery Prefetch

This instruction belongs to report item `replication.recovery_prefetch`. The item is backed by `replication.recovery_prefetch` (SQL query).

## What this item shows
- PostgreSQL 15+ cumulative `pg_stat_recovery_prefetch` decisions, reset age, current distances, and I/O depth.
- Prefetched and already-cached blocks plus skip reasons for initialization, missing blocks, full-page images, and recent prefetches.
- A primary can expose a zero-valued row; useful activity exists only while recovery is running.

## What to watch
- Whether prefetch and hit counts advance during recovery and which skip reason dominates.
- Replay lag and OS storage behavior alongside prefetch decisions.
- `recovery_prefetch` configuration and `effective_io_concurrency` before interpreting low activity.

## Automatic evaluation
- No automatic severity: useful ratios depend on recovery workload, cache state, and storage.
- Unsupported on PostgreSQL 10-14; a primary zero row is not a failure.

## Common fault causes
- Feature disabled, workload already cached, full-page images, new/zero-initialized blocks, or unsuitable access patterns.
- Storage saturation or low effective I/O concurrency.

## Checklist
- Interpret only with confirmed recovery activity and repeated captures.
- Use `prefetch_pct`/`hit_pct` as shares of recorded decisions, not cache hit ratios for normal SQL.
- Correlate with receive/replay gaps and OS I/O charts.
- Preserve the reset timestamp when comparing clusters.
