# Heavy And Failed Maintenance Events

This instruction belongs to report item `server_log.maintenance_events`. The item consumes the csvlog window collected with `--log-depth-time-min`.

## What this item shows
- Heavy successful autovacuum/autoanalyze plus failed, cancelled, blocked, or wraparound-related VACUUM, ANALYZE, and REINDEX evidence.
- A successful automatic run is included when at least one threshold is met: duration >= 5 seconds; scanned pages >= 128 MiB using the server `block_size`; buffer reads plus dirtied >= 128 MiB; or WAL >= 64 MiB.
- PostgreSQL 10-14 autovacuum messages do not publish `scanned`. For those versions the page-traffic threshold is unavailable: `relation_pages_after` is shown for context but is deliberately not treated as processed traffic. Duration, buffer, WAL, and tuple thresholds still apply. PostgreSQL 15 and newer messages expose scanned pages directly.
- Errors, cancellations, lock waits reported by `log_lock_waits`, and wraparound emergencies are always included. `impact_score` is the largest threshold ratio, so values above 1 identify the dimension that crossed a threshold.
- Cancelled autovacuum/autoanalyze workers are included even with an empty command tag. Their table and operation are recovered from CSV `CONTEXT` when available; missing completion statistics do not hide the cancellation.
- At most 100 qualifying series are emitted, ranked by impact. `below_threshold_event_count` records intentionally filtered successful noise; `omitted_series_count` warns when qualifying rows exceeded the fixed limit.

## What to watch
- High WAL or buffer volume, long elapsed time, repeated work on one relation, or many dead tuples that could not be removed.
- `wraparound_emergency`, `error_or_cancellation`, or `lock_wait` inclusion reasons: these outrank successful-volume evidence.
- Missing expected fields can reflect PostgreSQL-version/message-format differences; the thresholds use only metrics actually reported and parsed.

## Common fault causes
- Dead-tuple churn, cost delays, undersized worker capacity, old snapshots/replication slots, table/index bloat, or blocking DDL.
- Manual cancellation, statement/lock timeout, wraparound protection, or insufficient maintenance memory/storage.

## Automatic evaluation
- Heavy successful events are medium priority; failure/cancellation/wraparound evidence is high priority.
- Incomplete log coverage sets severity to `unknown` and makes counts lower bounds.
- A complete empty result means no recognized event exceeded the documented thresholds and no recognized failure/emergency occurred; it does not mean maintenance did not run.

## Related report items
- [server_log.autovacuum_runs](#item-server_log.autovacuum_runs) — Existing full chronology compatibility item.
- [server_log.wraparound_pressure](#item-server_log.wraparound_pressure) — Focused wraparound warnings.

## Checklist
- Start with the highest `impact_score`, verify relation churn and blockers, and compare autovacuum settings/reloptions with workload and table size.
- Do not lower logging thresholds indiscriminately; this item intentionally excludes successful low-impact runs to bound report size.
