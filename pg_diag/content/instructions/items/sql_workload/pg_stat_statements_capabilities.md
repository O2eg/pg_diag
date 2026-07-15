# pg_stat_statements Capability Check

This instruction belongs to report item `sql_workload.pg_stat_statements_capabilities`. The item is backed by `statements.pg_stat_statements_capabilities` (SQL query).

## What this item shows
- Package availability, extension installation/version/schema, and visibility of `pg_stat_statements` and `pg_stat_statements_info` in the connected database.
- Server preload, built-in query-ID mode, statement tracking, planning, utility, persistence, entry-limit, and I/O-timing settings.
- Whether the collection role can see query IDs/text for other roles and privileged configuration settings.

## What to watch
- The library not preloaded, the extension not installed in this database, or either view missing from pg_diag's `pg_catalog, public` search path.
- `pg_stat_statements.track = none`, which disables statement collection.
- `cross_user_query_visibility = current_user_only`; counters for other users remain visible, but their `queryid` and query text are hidden.
- `settings_visibility = restricted` or `preloaded = <hidden>`; absence of configuration evidence must not be interpreted as a missing preload entry.
- A small `pg_stat_statements.max` under high query churn. Evictions must be checked in `pg_stat_statements_info.dealloc` when the view is available.

## Automatic evaluation
- Evidence is `unknown` when required package/view/preload/query-ID/tracking capability is unavailable or cross-user identity is hidden.
- `track_io_timing = off`, planning tracking off, utility tracking off, `track = top`, and `save = off` are reported but not automatically treated as faults because they are policy and overhead choices.
- `compute_query_id` other than `on` or `auto` means built-in computation is not enabled; a third-party query-ID provider can still make tracking valid and must be verified separately.

## Common fault causes
- Package installed but not preloaded before restart, or `CREATE EXTENSION` omitted in the target database.
- Monitoring role lacks `pg_read_all_stats` by design.
- Tracking disabled or entry churn exceeds `pg_stat_statements.max`.
- Extension installed outside the restricted pg_diag search path.

## Checklist
- Fix activation gaps under the site's restart and change policy.
- Grant `pg_read_all_stats` only when cross-user SQL-text visibility is approved.
- Check `pg_stat_statements_info.stats_reset` and `dealloc` before interpreting cumulative rankings.
- Do not reset statistics merely to run pg_diag; pg_diag never calls `pg_stat_statements_reset()`.
- This item normally returns rows. A collection error means capability is unknown, not unavailable.
