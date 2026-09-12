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
- `stats_window_start` and `stats_window_source` give a lower bound of the counter window: the counters have accumulated at least since that moment. It is the latest of the postmaster start, `pg_stat_database.stats_reset` (exact when set; on PostgreSQL 15+ it stays NULL until `pg_stat_reset()` is called) and the shared statistics reset time (`pg_stat_bgwriter.stats_reset`). A shared reset after the postmaster started is either a crash recovery, which discards every counter, or a targeted `pg_stat_reset_shared()`, which leaves per-object counters older, so the later time never overstates the window; statistics also survive clean restarts, so the true window may be longer than shown. An object created after `stats_window_start` has accumulated only since its creation, which the catalog does not record.

## Related report items
- [snapshot_delta_workload.function_time_delta](#item-snapshot_delta_workload.function_time_delta) — Measure function activity during the capture window.
- [sql_workload.top_sql_by_total_time](#item-sql_workload.top_sql_by_total_time) — Check statements that may invoke expensive functions.

## Checklist
- Confirm track_functions setting.
- Profile functions with high self time.
- Inspect called SQL for high total time functions.
