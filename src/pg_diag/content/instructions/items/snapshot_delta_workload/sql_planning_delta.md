# SQL Planning Delta

This instruction belongs to report item `snapshot_delta_workload.sql_planning_delta`.

## What this item shows
- Statement plans and total planning time accumulated between endpoint snapshots.
- Planning rate and planning milliseconds per wall-clock second.

## What to watch
- High planning time relative to execution time and high plan counts caused by non-reused statements.

## Automatic evaluation
- No severity is assigned because planning cost varies widely by statement complexity.

## Interval coverage
- Collection depends on `pg_stat_statements.track_planning`; when it is off, planning counters remain zero.
- Statement and reset identity rules match the other pg_stat_statements Delta items.

## Common fault causes
- Complex joins, partition pruning, many relations, unprepared dynamic SQL, and frequent invalidation.

## Related report items
- [snapshot_delta_workload.sql_time_delta](#item-snapshot_delta_workload.sql_time_delta) — Compare planning and execution time for the same statements.
- [sql_workload.pg_stat_statements_capabilities](#item-sql_workload.pg_stat_statements_capabilities) — Verify planning-counter availability.

## Checklist
- Confirm `track_planning` in the table before interpreting an empty result.
- Compare planning time with SQL Time Delta and application statement reuse.
