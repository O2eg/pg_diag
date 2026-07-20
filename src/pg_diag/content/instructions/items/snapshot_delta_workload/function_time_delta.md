# Function Time Delta

This instruction belongs to report item `snapshot_delta_workload.function_time_delta`. The item is backed by `objects.function_time_delta` (snapshot metric).

## What this item shows
- Calls, total/self time deltas, calls/s, and total function milliseconds per second for stable function OIDs.
- Current schema/function labels with `(datid, funcid)` identity, so overloaded functions do not collapse by name.
- Up to 100 candidates selected by cumulative total time, then 50 derived rows.

## What to watch
- High total time/s, high call rate, and a large gap between total and self time indicating time in called functions.

## Automatic evaluation
- No severity is assigned because procedural function cost and expected invocation rates are workload-specific.
- Data exists only for function types enabled by `track_functions`; inlined SQL functions may not be represented as expected.

## Interval coverage
- Database-wide reset epoch and counter decreases are checked. A single-function reset has no timestamp and can evade detection if counters regrow above the start.
- OID identity distinguishes overloads and survives renames; drop/recreate or bounded Top-100 churn becomes unmatched coverage.

## Common fault causes
- Expensive procedural loops, nested function work, high call frequency, disabled tracking, reset, or selection churn.

## Related report items
- [object_workload.function_workload](#item-object_workload.function_workload) — Compare interval execution with cumulative function counters.
- [sql_workload.top_sql_by_total_time](#item-sql_workload.top_sql_by_total_time) — Check SQL that may invoke expensive functions.

## Checklist
- Confirm `track_functions` and whether the function can be inlined.
- Compare total versus self time and profile called SQL/functions.
- Treat the result as a bounded endpoint intersection, not a complete function inventory.
- Empty can mean no tracked calls, disabled tracking, or no comparable bounded candidate.
