# Database Workload Delta

This instruction belongs to report item `snapshot_delta_workload.database_workload_delta`. The item is backed by `database.workload_delta` (snapshot metric).

## What this item shows
- Start-to-end transaction, tuple, temp, deadlock, and database I/O deltas for the capture window.
- Current rates derived from database cumulative counters.

## What to watch
- Commit or rollback rate spike.
- Temp byte delta during the window.
- Deadlock delta greater than zero.

## Interval coverage
- A delta is calculated only when the database and counter value exist at both endpoints.
- Missing endpoint values are not converted to zero.
- Counter decreases or invalid timestamps are omitted and reported as invalid coverage.

## Common fault causes
- Traffic burst.
- Retry loop.
- Temp spill from concurrent queries.
- Deadlock-prone transaction ordering.

## Checklist
- Use this for current workload rate rather than long-term totals.
- Check capture duration before comparing rates.
- Follow spikes into SQL and chart sections.
