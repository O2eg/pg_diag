# Database Kernel CPU Rate

This instruction belongs to report item `snapshot_charts_db.database_kernel_cpu_rate`. The item is backed by `database.kernel_cpu_rate` (snapshot metric).

## What this item shows
- Stacked user and system execution CPU rates from top-level `pg_stat_kcache` entries, partitioned by database.
- The chart unit is `CPU-s/s`: `1.0` means one logical CPU fully occupied during an interval, and totals can exceed `1.0` with concurrency.
- Repeated samples form the incident timeline; the first point has no preceding interval and therefore no rate.

## What to watch
- Total stack approaching host/cgroup CPU capacity.
- A rising system-CPU share during I/O, page-fault, or syscall-heavy intervals.
- Gaps after entry churn or counter decreases; a gap is invalid coverage, not zero CPU.

## Automatic evaluation
- No fixed severity is assigned because available cores and CPU quotas are deployment-specific.
- Only top-level entries are aggregated to avoid nested-statement double counting.

## Common fault causes
- Concurrent CPU-heavy queries, plan regression, parallel work, or background application bursts.
- Kernel/filesystem work, memory faults, and scheduler pressure increasing system CPU.
- CPU quotas or noisy-neighbor contention reducing effective capacity.

## Related report items
- [snapshot_delta_workload.sql_kernel_cpu_delta](#item-snapshot_delta_workload.sql_kernel_cpu_delta) — Attribute a database CPU interval to statement identities.
- [snapshot_charts_os.os_cpu_utilization](#item-snapshot_charts_os.os_cpu_utilization) — Compare database-attributed CPU with total host CPU.
- [snapshot_charts_os.os_cpu_load](#item-snapshot_charts_os.os_cpu_load) — Check runnable-queue pressure.
- [snapshot_charts_db.database_page_fault_rate](#item-snapshot_charts_db.database_page_fault_rate) — Correlate CPU changes with memory faults.

## Checklist
- Compare the stack with CPU count and cgroup quotas, not with a hard-coded 100%.
- Drill into the SQL CPU delta for the same interval.
- Treat missing extension/native evidence as unavailable, not zero.
- Empty means fewer than two comparable samples or no non-zero CPU delta; `unsupported` normally means pg_stat_kcache 2.3+ is unavailable.
