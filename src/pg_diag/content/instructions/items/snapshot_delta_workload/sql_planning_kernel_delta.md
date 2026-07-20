# SQL Planning Kernel Delta

This instruction belongs to report item `snapshot_delta_workload.sql_planning_kernel_delta`. The item is backed by `statements.planning_kernel_delta` (snapshot metric).

## What this item shows
- Planning user/system CPU, CPU seconds/s, CPU milliseconds per plan, filesystem reads/writes, page faults, and context switches by SQL identity.
- `CPU-s/s = 1.0` is one logical CPU consumed continuously; byte and count fields are interval deltas and `ms/plan` divides planning CPU by plans.
- PostgreSQL 13+ only, and rows are collected only while `pg_stat_kcache.track_planning = on`; `query_id` is clickable.

## What to watch
- High planning CPU per plan or rate, especially with many near-unique statements.
- Planning major faults, filesystem bytes, or involuntary switches accompanying latency.
- Empty data with planning tracking off; consult the capability item before treating it as no planning cost.

## Automatic evaluation
- No fixed severity is assigned because planning budgets and acceptable parse/plan frequency depend on workload and pooling mode.
- Changed `stats_since`, reset/decreased counters, PostgreSQL below 13, and disabled planning tracking prevent a valid interval.

## Interval coverage
- The same query identity and unchanged `pg_stat_kcache.stats_since` must be present at both window endpoints.
- Candidate churn and reset/decreased planning or plan counters are omitted; per-plan ratios use only accepted deltas.

## Common fault causes
- Unparameterized SQL producing many query identities or repeated replanning.
- Large partition/inheritance catalogs, complex joins, many statistics objects, or invalidation churn.
- CPU contention, cold catalog pages, and memory pressure during planning.

## Related report items
- [sql_workload.pg_stat_kcache_capabilities](#item-sql_workload.pg_stat_kcache_capabilities) — Verify version and planning-tracking prerequisites.
- [snapshot_delta_workload.sql_planning_delta](#item-snapshot_delta_workload.sql_planning_delta) — Compare kernel planning cost with pg_stat_statements plan counts/timing.
- [snapshot_delta_workload.sql_kernel_cpu_delta](#item-snapshot_delta_workload.sql_kernel_cpu_delta) — Compare planning and execution CPU for the same query.
- [sql_workload.pg_stat_statements_capabilities](#item-sql_workload.pg_stat_statements_capabilities) — Verify statement planning counters and query identity support.

## Checklist
- Confirm PostgreSQL 13+, pg_stat_kcache 2.3+, and both planning trackers before interpreting rows.
- Compare CPU per plan with plan frequency to separate expensive planning from excessive replanning.
- Review parameterization and invalidation causes before enabling long-lived plan caching.
- Empty with tracking on means no non-zero comparable candidate; `unsupported` indicates a missing version/API prerequisite.
