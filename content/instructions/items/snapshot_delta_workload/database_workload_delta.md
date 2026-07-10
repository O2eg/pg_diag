# Database Workload Delta

This instruction belongs to report item `snapshot_delta_workload.database_workload_delta`. The item is backed by `database.workload_delta` (snapshot metric).

## What this item shows
- Current-database transaction, block, tuple, temporary-file, deadlock, and backend I/O-time changes between two window endpoints.
- Deltas plus selected per-second rates calculated from the actual endpoint timestamps.
- `commit_delta_raw`, the known `pg_diag_commit_overhead`, and `commit_delta`/`commits_per_sec` after subtracting pg_diag's own batched read-only transactions.

## What to watch
- Rollback or transaction-rate growth, temp bytes/files, and deadlocks during the capture window.
- Large block-read bytes or read/write time when `track_io_timing` is enabled.
- Tuple counters as database access activity, not rows returned to the client: PostgreSQL counter semantics include internal scan/index activity.

## Automatic evaluation
- `medium`: one or more deadlocks occurred between endpoints.
- Other rates do not assign severity because workload volume and service objectives are deployment-specific.
- If PostgreSQL has not exposed all collector commits by the end read, the adjusted commit fields remain null rather than being forced to zero.

## Interval coverage
- Database OID is the identity and `pg_stat_database.stats_reset` is the counter epoch.
- An epoch change, counter decrease, invalid value, or invalid interval omits the row and emits invalid coverage.
- The raw commit counter includes monitoring transactions. pg_diag executes one outer read-only transaction per endpoint/sample batch and subtracts the exact number between these endpoints.
- Only commit and total-transaction fields are adjusted. Block, tuple, temporary-file, and I/O-time deltas remain raw PostgreSQL counters and can include work performed by pg_diag's chart and endpoint SELECTs; their collector contribution cannot be subtracted exactly.

## Common fault causes
- Traffic or retry burst, temp-spilling SQL, storage latency, or deadlock-prone lock ordering.
- External statistics reset during collection.
- `track_io_timing = off`, which leaves timing deltas at zero while block counters remain valid.

## Checklist
- Confirm capture duration and interval coverage before comparing rates.
- Follow deadlocks into PostgreSQL logs and lock evidence.
- Correlate tuple, block, temp, and transaction changes with SQL and object delta items.
- Treat small tuple/block/temp deltas on an otherwise idle database as possible collector self-observation; compare them with application workload before drawing a conclusion.
- Empty means no non-zero comparable delta; invalid coverage or source failure is not evidence of zero workload.
