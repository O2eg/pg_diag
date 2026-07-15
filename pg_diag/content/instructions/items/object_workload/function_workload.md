# Function Workload Counters

This instruction belongs to report item `object_workload.function_workload`. The item is backed by `objects.function_workload` (SQL query).

## What this item shows
- User-defined function calls and total/self execution time.
- Procedural code workload visible through pg_stat_user_functions.
- Whether track_functions exposes function-level cost.

## What to watch
- High total_time or self_time for one function.
- Very high function call count.
- Empty result when function tracking was expected.

## Common fault causes
- Expensive PL/pgSQL loops.
- Functions hiding SQL calls.
- track_functions disabled or set too narrowly.
- Application overusing procedural helper.

## Automatic evaluation
- This item is informational because function cost is workload-specific.
- Counters are cumulative from `stats_reset`; an empty result is expected when `track_functions=none`.
- Overloaded functions are distinguished by OID and identity arguments, and output is limited to 100 rows.

## Checklist
- Confirm track_functions setting.
- Profile functions with high self time.
- Inspect called SQL for high total time functions.
