# Function Time Delta

This instruction belongs to report item `snapshot_delta_workload.function_time_delta`. The item is backed by `objects.function_time_delta` (snapshot metric).

## What this item shows
- Per-function call and time deltas during the capture window.
- Procedural code consuming time during snapshots mode.

## What to watch
- High function time per second.
- High call rate for a PL function.
- Missing data because track_functions is disabled.

## Interval coverage
- The SQL source is sorted and limited before rows enter collector memory.
- Only functions present in both bounded endpoint selections have a calculable delta.
- `missing_start` and `missing_end` are expected selection churn, not zero activity or errors.
- Counter decreases or invalid values are omitted and reported as invalid coverage.

## Common fault causes
- Expensive PL/pgSQL loops.
- Function hides SQL work.
- Application calls function too frequently.

## Checklist
- Confirm `track_functions` setting.
- Profile high-time functions.
- Review function body and called SQL.
