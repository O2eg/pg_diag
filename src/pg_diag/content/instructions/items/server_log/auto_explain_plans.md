# Top Auto Explain Queries By Minute

This instruction belongs to report item `server_log.auto_explain_plans`. The item is backed by `server_log.auto_explain_plans` (trusted Python source) and consumes the csvlog window collected with `--log-depth-time-min`.

## What this item shows
- A stacked-column time series with one clock-aligned column per minute and no more than ten query blocks in each column.
- Every block is one `auto_explain` event and its height is proportional to that query's duration. The stack is ordered top-to-bottom from longest to shortest within its minute.
- Colors are positional rather than legend categories: the longest, top block is red; the shortest, bottom block is yellow; intermediate blocks use distinct transition colors between them.
- Hovering a block shows the event's exact log timestamp, duration, and a sanitized query sample capped at 300 characters. The legend is intentionally hidden because ranks and queries can change every minute.
- Clicking a block opens the plan in the report's bundled `pg-explain-viewer`. This embedded view is read-only and offline; it has no input editor or export action.
- JSON, text, XML, and YAML plan bodies are recognized. The artifact never retains the original raw plan: only collector-sanitized data, bounded by the auto-explain record limit, is available to the viewer. XML is converted to an equivalent sanitized JSON structure because the embedded viewer natively accepts text, JSON, and YAML.

## What to watch
- A tall red top segment: the slowest query dominates that minute's observed execution time.
- A sudden increase in slower bands after a deployment or maintenance event.
- `omitted_plan_count` above zero: at least one minute contained more than ten plans, so shorter plans were intentionally left out of the chart.
- `parsed_plan_count` below `plan_count`: oversized, incomplete, or unrecognized plan records need direct log review.

## Common fault causes
- Missing indexes, stale statistics, cardinality-estimation errors, or an unsuitable join strategy.
- I/O pressure, lock contention, memory spills, or a working set larger than cache.
- An overly low `auto_explain.log_min_duration` or high `auto_explain.sample_rate` producing more log volume than the bounded collector can return.

## Automatic evaluation
- The chart is observational and does not label a slow plan as a failure by itself.
- Incomplete log coverage or plan bodies set severity to `unknown`; all counts may then be lower bounds.
- A complete window with no matching records is reported as empty, while an incomplete empty window does not claim that no plans occurred.

## Related report items
- [sql_workload.top_sql_by_total_time](#item-sql_workload.top_sql_by_total_time) — Aggregate statement load and query IDs.
- [activity_locks.wait_event_sample_profile](#item-activity_locks.wait_event_sample_profile) — Wait-event pressure during snapshots.
- [server_log.lock_waits](#item-server_log.lock_waits) — Logged blocking that can inflate execution duration.

## Checklist
- Prefer `auto_explain.log_format = json` for the strongest parser validation.
- Keep `auto_explain.log_parameter_max_length = 0` and review the exposure risk of query text in server logs.
- Correlate the affected bucket with workload changes, waits, CPU, disk latency, and query statistics before changing SQL or indexes.
