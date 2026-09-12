# Query Time And Temporary File Events

This instruction belongs to report item `server_log.query_resource_events`. The item consumes the csvlog window collected with `--log-depth-time-min`.

## What this item shows
- Slow-statement duration records and temporary-file creation grouped by event type, query identity, database, and application.
- Occurrence count, first/last time, max/total duration, max/total temporary bytes, query ID, and a sanitized 300-character SQL sample.
- Only completed `statement` and `execute` duration records count as slow statements; auto_explain plans, parse/bind timings, and bare `log_duration` records do not add executions.
- A missing or zero query ID falls back to sanitized SQL identity. If both query ID and SQL are unavailable, a group contains unattributed message-pattern evidence within its database/application; it does not identify a specific query.
- At most 100 groups ranked by temporary bytes and duration; `omitted_aggregate_count` explicitly reports discarded lower-impact groups.
- `collector_generated = true` marks groups produced by pg_diag's own sampling queries (`/* pg_diag:` marker or `application_name = pg_diag`); they are listed last, excluded from the summary counts and ignored by the diagnostic graph.
- Groups are keyed by event type, query identity, application and database; the same query from two databases is two groups. Temporary-file records written while a backend exits carry no database: they join the database group with the same identity only when exactly one exists (`database_partial = true` on that group); with several candidate databases they stay a separate group with an empty `database_name` and `database_partial = true`, so the ambiguity remains visible.

## What to watch
- Large/repeated temporary files, rising total spill volume, or one query dominating total duration.
- Missing SQL samples: logging settings or event context did not expose a query; use query_id and application/database dimensions.

## Common fault causes
- Sort/hash/window operations exceeding effective memory, bad estimates/plans, missing indexes, or reporting queries scanning too much data.
- `log_min_duration_statement` or `log_temp_files` configured too high hides smaller events; too low creates excessive log volume.

## Automatic evaluation
- Matched resource events are medium-priority evidence, not proof of a bad query by themselves.
- Incomplete log coverage sets severity to `unknown`; totals then are lower bounds.
- A complete empty result only covers events visible under the active logging thresholds.

## Related report items
- [server_log.auto_explain_plans](#item-server_log.auto_explain_plans) — Logged execution plans.
- [sql_workload.top_sql_by_total_time](#item-sql_workload.top_sql_by_total_time) — Statement-level cumulative load.

## Checklist
- Inspect the largest totals/maxima first; verify plans, estimates, indexes, statistics, and effective `work_mem` before tuning.
- Keep logging thresholds selective enough to retain useful evidence without a log flood.
