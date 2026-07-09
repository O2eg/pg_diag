# SQL Time Delta

This instruction belongs to report item `snapshot_delta_workload.sql_time_delta`. The item is backed by `statements.total_time_delta` (snapshot metric).

## What this item shows
- Per-statement execution-time delta and rate across the snapshot window.
- Which SQL consumed time during this capture, not historically.

## What to watch
- High exec_time_ms_per_sec for one query_id.
- Short-window SQL hotspot different from cumulative Top SQL.
- Negative/missing deltas after stats reset.

## Interval coverage
- The SQL source is sorted and limited before rows enter collector memory.
- Only statements present in both bounded endpoint selections have a calculable delta.
- `missing_start` and `missing_end` are expected selection churn, not zero activity or errors.
- A counter decrease may indicate an external statistics reset or entry replacement; it is omitted rather than converted to zero.

## Common fault causes
- Incident-window workload differs from historical workload.
- pg_stat_statements reset during capture.
- Bursting batch job.

## Checklist
- Prioritize statements active in the incident window.
- Compare with Top SQL by total time.
- Capture EXPLAIN for top delta statements.
