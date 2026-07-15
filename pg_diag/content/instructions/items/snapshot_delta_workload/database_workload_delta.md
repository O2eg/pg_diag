# Database Workload Delta

This instruction belongs to report item `snapshot_delta_workload.database_workload_delta`. The item is backed by `database.workload_delta` (snapshot metric).

## What this item shows
- Per-database transaction, block, tuple, temporary-file, deadlock, and backend I/O-time changes between two window endpoints for all named databases.
- Deltas plus selected per-second rates calculated from the actual endpoint timestamps.
- Transaction deltas and rates come directly from `pg_stat_database`; the small amount of read-only collector activity is not adjusted out.

## What to watch
- Rollback or transaction-rate growth, temp bytes/files, and deadlocks during the capture window.
- Large block-read bytes or read/write time when `track_io_timing` is enabled.
- Tuple counters as database access activity, not rows returned to the client: PostgreSQL counter semantics include internal scan/index activity.

## Automatic evaluation
- `medium`: one or more deadlocks occurred between endpoints.
- Other rates do not assign severity because workload volume and service objectives are deployment-specific.
- Rows with zero activity remain visible so the table preserves the complete set of comparable databases.

## Interval coverage
- Database OID is the identity and `pg_stat_database.stats_reset` is the counter epoch.
- An epoch change, counter decrease, invalid value, or invalid interval omits the row and emits invalid coverage.
- PostgreSQL counters include monitoring activity. pg_diag does not apply hidden corrections to commit, tuple, block, temporary-file, or I/O-time values.
- The collector's SQL runs in the connection database, so only that database can include pg_diag's own read-only transactions and query work.

## Common fault causes
- Traffic or retry burst, temp-spilling SQL, storage latency, or deadlock-prone lock ordering.
- External statistics reset during collection.
- `track_io_timing = off`, which leaves timing deltas at zero while block counters remain valid.

## Checklist
- Confirm capture duration and interval coverage before comparing rates.
- Follow deadlocks into PostgreSQL logs and lock evidence.
- Correlate tuple, block, temp, and transaction changes with SQL and object delta items.
- Treat small deltas in the connection database as possible collector self-observation; compare them with application workload before drawing a conclusion.
- Empty means no database was comparable across both endpoints; invalid coverage or source failure is not evidence of zero workload.
