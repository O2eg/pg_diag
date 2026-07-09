# Current Database Statistics

This instruction belongs to report item `overview.database_stats`. The item is backed by `database.database_stats` (SQL query).

## What this item shows
- Cumulative `pg_stat_database` counters for the current database.
- Commits, rollbacks, tuple activity, block hits/reads, temp files, deadlocks, and I/O timing where available.
- PostgreSQL 18 parallel-worker launch demand and successful launches.
- Long-term workload shape since the last statistics reset.

## What to watch
- High rollback count or rollback ratio.
- Deadlocks greater than zero.
- Temp bytes or temp files growing.
- Block reads high relative to block hits.

## Automatic evaluation
- Checksum failures produce `high` because they are direct corruption evidence when checksums are enabled.
- One or more invalid indexes or cumulative deadlocks produce `medium`.
- Rollback ratio, cache-hit ratio, temporary activity, and I/O totals are not automatically classified because safe thresholds depend on reset age and workload.
- The summary is based on cumulative counters, not on activity confined to the snapshots window.

## Common fault causes
- Application errors or retry loops.
- Sort/hash spills to temporary files.
- Missing indexes, cold cache, or workload larger than effective cache.
- Transaction ordering problems causing deadlocks.

## Checklist
- Check `stats_reset` before interpreting cumulative totals.
- Use the separate Statistics Reset Times item because this row does not include its own reset timestamp.
- Use snapshot delta items for current rates.
- Follow high-level symptoms into SQL workload, object workload, wait, and I/O sections.
