# Top SQL By Calls

This instruction belongs to report item `sql_workload.top_sql_by_calls`. The item is backed by `statements.top_by_calls` (SQL query).

## What this item shows
- Up to 50 current-database entries ranked by cumulative completed execution count.
- Total/mean execution time, rows, shared blocks, version-dependent WAL, statement identity, and representative SQL.
- PostgreSQL 10-13 has no `toplevel` field, so it is reported as unavailable; `stats_since` exists on PostgreSQL 17+ and is unavailable on PostgreSQL 10-16.

## What to watch
- High-frequency queries with non-trivial mean time, I/O, WAL, or connection occupancy.
- N+1 patterns and repeated single-row operations that could be batched or cached.
- High calls caused by nested statements when `toplevel = false` and tracking is `all`.

## Automatic evaluation
- Call count alone does not assign severity; a frequent cheap query can be healthy.
- `unknown` indicates that query ID/text is hidden for at least one returned owner.
- Counts are cumulative and can survive restart when `pg_stat_statements.save = on`; the Top 50 is bounded before collection.

## Common fault causes
- N+1 application behavior, missing cache/batching, aggressive health checks, or retry loops.
- Legitimate high-throughput prepared statements.
- Statistics retained for a long period or entries repeatedly evicted/recreated.

## Checklist
- Establish the counter window from `stats_reset` and `stats_since` where available.
- Prioritize only after combining calls with time, I/O, WAL, and business value.
- Fix the application call pattern rather than merely suppressing its visibility.
- Empty means no tracked current-database entries; unsupported means the extension view is unavailable.
