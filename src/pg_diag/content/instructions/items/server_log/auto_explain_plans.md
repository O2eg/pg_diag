# Top Auto Explain Queries By Time Bucket

This instruction belongs to report item `server_log.auto_explain_plans`. The item is backed by `server_log.auto_explain_plans` (trusted Python source) and consumes the csvlog window collected with `--log-depth-time-min`.

## What this item shows
- A stacked-column time series selects the 2000 slowest auto_explain executions across the entire collected window, then displays at most the 15 slowest retained executions per clock-aligned bucket. `settings.bucket_seconds` sets the bucket width: 60 (default) for a minute or 300 for five minutes. The per-bucket cap does not refill the global selection with faster executions.
- A bounded Python dictionary and min-heap evict the lowest-duration execution when a slower one arrives. Equal durations keep earlier input events. Repeated SQL retains separate executions and plans; the shared SQL dictionary is not pruned.
- The summary separates global eviction (`evicted_plan_count`) from the additional bucket cap (`bucket_omitted_plan_count`). Their sum is `omitted_plan_count`. `global_retained_plan_count` counts executions after the global limit; `displayed_plan_count` counts those remaining after both limits. `minimum_retained_duration_ms` records the global selection threshold.
- Plan references are populated only after selection, slowest first, so evicted plans do not consume the reference budget. A separate 64 MiB plan payload limit can still omit plan bodies; this is reported separately.
- The time axis shows date and time and spans displayed events only; synthetic zero points do not extend it to the collection window boundaries.
- Every block is one `auto_explain` event and its height is proportional to that query's duration. The stack is ordered top-to-bottom from longest to shortest within its bucket.
- Colors are positional rather than legend categories: the longest, top block is red; the shortest, bottom block is yellow; intermediate blocks use distinct transition colors between them.
- Hovering a block shows the event's exact log timestamp, duration, and a sanitized query sample capped at 300 characters. The legend is intentionally hidden because ranks and queries can change every bucket.
- Clicking a block opens the plan in the report's bundled `pg-explain-viewer`. This embedded view is read-only and offline; it has no input editor or export action.
- JSON, text, XML, and YAML plan bodies are recognized. The artifact never retains the original raw plan: only collector-sanitized data, bounded by the auto-explain record limit, is available to the viewer. XML is converted to an equivalent sanitized JSON structure because the embedded viewer natively accepts text, JSON, and YAML.

## What to watch
- A tall red top segment: the slowest query dominates that bucket's displayed execution time.
- A sudden increase in slower bands after a deployment or maintenance event.
- `omitted_plan_count` above zero: executions were excluded by the global or per-bucket limit. This chart describes the slowest executions, not frequency or total workload. A chart end before the collected window end does not prove that later plans are absent from the logs.
- `parsed_plan_count` below `plan_count`: oversized, incomplete, or unrecognized plan records need direct log review.

## Common fault causes
- Missing indexes, stale statistics, cardinality-estimation errors, or an unsuitable join strategy.
- I/O pressure, lock contention, memory spills, or a working set larger than cache.
- An overly low `auto_explain.log_min_duration` or high `auto_explain.sample_rate` producing more log volume than the bounded collector can return.

## Automatic evaluation
- The chart is observational and does not label a slow plan as a failure by itself.
- Duration-based eviction alone does not mark collection as incomplete. Incomplete log coverage, unparsed/truncated plan records, or missing reference payloads set severity to `unknown`; counts are lower bounds when collection coverage is incomplete.
- A complete window with no matching records is reported as empty, while an incomplete empty window does not claim that no plans occurred.

## Related report items
- [sql_workload.top_sql_by_total_time](#item-sql_workload.top_sql_by_total_time) — Aggregate statement load and query IDs.
- [activity_locks.wait_event_sample_profile](#item-activity_locks.wait_event_sample_profile) — Wait-event pressure during snapshots.
- [server_log.lock_waits](#item-server_log.lock_waits) — Logged blocking that can inflate execution duration.

## Checklist
- Prefer `auto_explain.log_format = json` for the strongest parser validation.
- Keep `auto_explain.log_parameter_max_length = 0` and review the exposure risk of query text in server logs.
- Correlate the affected bucket with workload changes, waits, CPU, disk latency, and query statistics before changing SQL or indexes.
