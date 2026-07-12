# Database Statistics

This instruction belongs to report item `overview.database_stats`. The item is backed by `database.database_stats` (SQL query).

## What this item shows
- Cumulative `pg_stat_database` counters for every database in the cluster.
- Commits, rollbacks, tuple activity, block hits/reads, temp files, deadlocks, and I/O timing where available.
- PostgreSQL 18 parallel-worker launch demand and successful launches.
- Per-database statistics reset timestamps and long-term workload shape since each reset.

## What to watch
- High rollback count or rollback ratio.
- Deadlocks greater than zero.
- Temp bytes or temp files growing.
- Block reads high relative to block hits.

## Automatic evaluation
- Checksum failures produce `high` because they are direct corruption evidence when checksums are enabled.
- One or more cumulative deadlocks in a database produce `medium`.
- Rollback ratio, cache-hit ratio, temporary activity, and I/O totals are not automatically classified because safe thresholds depend on reset age and workload.
- The summary is based on cumulative counters, not on activity confined to the snapshots window.

## Common fault causes
- Application errors or retry loops.
- Sort/hash spills to temporary files.
- Missing indexes, cold cache, or workload larger than effective cache.
- Transaction ordering problems causing deadlocks.

## Checklist
- Compare `stats_reset` between databases before interpreting cumulative totals.
- Correlate cluster-level reset history with the separate Statistics Reset Times item.
- Use snapshot delta items for current rates.
- Follow high-level symptoms into SQL workload, object workload, wait, and I/O sections.
