# SQL Shared I/O Delta

This instruction belongs to report item `snapshot_delta_workload.sql_io_delta`. The item is backed by `statements.io_delta` (snapshot metric).

## What this item shows
- Shared block read/write and I/O-time deltas for statement entries present at both endpoints.
- Read/write block rates plus full `(dbid, userid, queryid, toplevel)` identity.
- Up to 50 candidates selected by cumulative shared blocks read at each endpoint.

## What to watch
- High shared reads per second and read-time delta during host I/O pressure.
- Backend block writes from statements expected to be read-only.
- Timing values at zero when `track_io_timing` is disabled; block counters remain usable.

## Automatic evaluation
- No severity is assigned because block volume and acceptable latency depend on workload and cache state.
- Shared block reads mean PostgreSQL buffer misses that requested a read; operating-system cache can still satisfy them without physical device I/O.

## Interval coverage
- Statement key and reset/entry epochs use the same contract as `SQL Time Delta`.
- Changed epochs, decreases, and invalid timestamps are omitted as invalid coverage.
- Top-50 selection churn is reported as `missing_start`/`missing_end` and is not converted to zero.

## Common fault causes
- Batch scans, cache-miss bursts, bulk DML, plan changes, or pg_stat_statements reset/eviction.

## Checklist
- Compare with table I/O and OS device latency at the same window.
- Review safe representative plans with `BUFFERS`.
- Do not equate shared block writes with all eventual checkpoint writes.
- Empty/unsupported semantics follow the SQL Time and capability items.
