# SQL Kernel CPU Delta

This instruction belongs to report item `snapshot_delta_workload.sql_kernel_cpu_delta`. The item is backed by `statements.kernel_cpu_delta` (snapshot metric).

## What this item shows
- Execution user/system CPU deltas from `pg_stat_kcache`, total CPU seconds, CPU seconds per wall-clock second, and the system-CPU share for each SQL identity.
- `CPU-s/s` means CPU seconds accumulated per wall-clock second: `1.0` is one fully occupied logical CPU and concurrent work can exceed `1.0`.
- Up to 50 comparable rows from an independently collected 250-entry endpoint candidate set; `query_id` opens the captured statement text.

## What to watch
- Sustained high `cpu_seconds_per_sec`, especially when it approaches the CPUs available to PostgreSQL.
- High `system_cpu_pct`, which points toward kernel work, syscalls, memory management, or filesystem activity rather than SQL computation alone.
- A statement absent at either endpoint is coverage churn, not zero CPU.

## Automatic evaluation
- No fixed severity is assigned because CPU budgets depend on concurrency, CPU limits, and workload objectives.
- Only top-level `pg_stat_kcache` entries are used to avoid double counting when extension tracking includes nested statements.

## Interval coverage
- Per-entry `pg_stat_kcache.stats_since` must be unchanged and all required counters must be monotonic between endpoints.
- `missing_start`/`missing_end` reflects candidate-set or entry churn; reset/decrease intervals are omitted rather than reported as zero.

## Common fault causes
- CPU-heavy expressions, joins, aggregation, decompression, or JIT work.
- Frequent syscalls, page faults, filesystem I/O, or scheduler pressure increasing system CPU.
- Plan regression or a burst of concurrent executions.

## Related report items
- [snapshot_delta_workload.sql_cpu_efficiency_delta](#item-snapshot_delta_workload.sql_cpu_efficiency_delta) — Compare CPU with calls and elapsed execution time.
- [snapshot_delta_workload.sql_context_switches_delta](#item-snapshot_delta_workload.sql_context_switches_delta) — Check scheduler switching for the same query ID.
- [snapshot_charts_db.database_kernel_cpu_rate](#item-snapshot_charts_db.database_kernel_cpu_rate) — Place statement CPU inside the database-level timeline.
- [snapshot_charts_os.os_cpu_utilization](#item-snapshot_charts_os.os_cpu_utilization) — Compare attributed PostgreSQL CPU with host CPU saturation.

## Checklist
- Verify `sql_workload.pg_stat_kcache_capabilities` before interpreting missing rows.
- Compare the same four-part identity `(dbid, userid, query_id, toplevel)` across related tables.
- Inspect a representative plan only when execution is safe.
- Empty means no non-zero comparable candidate; `unsupported` normally means pg_stat_kcache 2.3+ is unavailable.
