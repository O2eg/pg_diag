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

## Checklist
- Confirm track_functions setting.
- Profile functions with high self time.
- Inspect called SQL for high total time functions.
