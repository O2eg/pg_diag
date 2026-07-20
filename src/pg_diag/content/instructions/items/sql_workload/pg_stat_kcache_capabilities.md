# pg_stat_kcache Capability Check

This instruction belongs to report item `sql_workload.pg_stat_kcache_capabilities`. The item is backed by `statements.pg_stat_kcache_capabilities` (SQL query).

## What this item shows
- Package and extension availability, installed version/schema, raw function presence, and the 2.3+ `stats_since` delta API.
- Whether `pg_stat_statements` is installed and ordered before `pg_stat_kcache` in `shared_preload_libraries`.
- Execution/planning tracking modes and the Linux timer-frequency override visible to the collection role.

## What to watch
- `delta_api_2_3 = false`: interval items deliberately remain unsupported because entry resets and reuse cannot be identified safely.
- Missing preload, `preload_order = incorrect/incomplete`, or `pg_stat_kcache.track = none`.
- `preloaded = <hidden>` means insufficient settings visibility, not proof that the library is absent.
- Planning diagnostics require PostgreSQL 13+ and `pg_stat_kcache.track_planning = on`.

## Automatic evaluation
- Required extension, function, 2.3+ API, pg_stat_statements, preload, and execution tracking gaps are reported as `unknown` because the kernel evidence cannot be collected reliably.
- Planning tracking off is informational: enabling it has overhead and must be an explicit operational decision.

## Common fault causes
- The package is installed but the server was not restarted after changing preload libraries.
- `CREATE EXTENSION pg_stat_kcache` was omitted in the connected database or the SQL extension version is older than the loaded library.
- `pg_stat_kcache` appears before `pg_stat_statements` in the preload list.
- The monitoring role cannot read all settings.

## Related report items
- [sql_workload.pg_stat_statements_capabilities](#item-sql_workload.pg_stat_statements_capabilities) — Verify the query identity and workload-statistics dependency.
- [snapshot_delta_workload.sql_kernel_cpu_delta](#item-snapshot_delta_workload.sql_kernel_cpu_delta) — Confirm that execution kernel CPU deltas are available.
- [snapshot_delta_workload.sql_planning_kernel_delta](#item-snapshot_delta_workload.sql_planning_kernel_delta) — Confirm planning tracking before interpreting an empty planning table.

## Checklist
- Require pg_stat_kcache 2.3+ for these delta items.
- Keep `pg_stat_statements` before `pg_stat_kcache` in `shared_preload_libraries`.
- Enable planning tracking only after evaluating overhead on representative load.
- Do not reset statistics merely to run pg_diag; pg_diag never calls `pg_stat_kcache_reset()`.
- Empty rows mean the capability query itself failed to produce evidence; inspect collection diagnostics.
