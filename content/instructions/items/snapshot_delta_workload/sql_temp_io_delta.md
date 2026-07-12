# SQL Temp I/O Delta

This instruction belongs to report item `snapshot_delta_workload.sql_temp_io_delta`.

## What this item shows
- Statements that read or wrote temporary blocks between the two endpoint snapshots.
- Temporary bytes, block counts, I/O time, and byte rate for each stable statement identity.

## What to watch
- Large writes usually indicate sorts, hashes, materialization, or other operations spilling beyond available working memory.
- Read-back after writes indicates multi-pass temporary processing.

## Automatic evaluation
- No universal severity is assigned because acceptable temporary I/O depends on concurrency, query shape, and storage.

## Interval coverage
- Rows require the same `(dbid, userid, queryid, toplevel)` at both bounded Top-50 endpoints and unchanged pg_stat_statements reset epochs.
- Missing endpoint membership and counter resets are omitted rather than converted to zero.

## Common fault causes
- Underestimated row counts, insufficient per-operation memory, wide rows, large aggregates, and concurrent analytical queries.

## Checklist
- Resolve the query ID in the cumulative SQL items and inspect its execution plan.
- Correlate temporary bytes with database and operating-system I/O before changing memory settings.
