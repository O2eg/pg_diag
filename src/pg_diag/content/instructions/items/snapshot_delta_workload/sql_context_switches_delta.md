# SQL Context Switches Delta

This instruction belongs to report item `snapshot_delta_workload.sql_context_switches_delta`. The item is backed by `statements.context_switches_delta` (snapshot metric).

## What this item shows
- Voluntary and involuntary context-switch deltas/rates, switches per call, and involuntary switches per CPU second from execution counters.
- `/s` values are switches per wall-clock second; per-call and per-CPU-second fields are ratios of interval deltas.
- Up to 50 comparable SQL identities from an independent 250-entry endpoint candidate set, with clickable `query_id`.

## What to watch
- High involuntary switching per CPU second, often associated with CPU contention or scheduler preemption.
- High voluntary switching per call, which can accompany waits, blocking, sleep, or frequent synchronization.
- Platform-unavailable counters; they are omitted and must not be read as proven zero switching.

## Automatic evaluation
- No fixed severity is assigned because normal switch rates vary greatly by kernel, CPU count, and workload shape.
- Counter decreases and changed `stats_since` epochs invalidate the complete row interval.

## Interval coverage
- Both endpoints must contain the same query identity with an unchanged `pg_stat_kcache.stats_since` epoch.
- Missing/native-null counters do not become zeros; invalid and unmatched intervals are summarized separately.

## Common fault causes
- CPU oversubscription, restrictive cgroup quotas, or many runnable PostgreSQL processes.
- Lock/I/O waits and frequent latch, process, or extension synchronization.
- Very short, high-frequency executions amplifying scheduling overhead.

## Related report items
- [snapshot_delta_workload.sql_kernel_cpu_delta](#item-snapshot_delta_workload.sql_kernel_cpu_delta) — Compare switches with CPU consumption for the same query.
- [snapshot_delta_workload.sql_page_faults_delta](#item-snapshot_delta_workload.sql_page_faults_delta) — Check whether memory faults accompany scheduling churn.
- [snapshot_charts_os.os_cpu_load](#item-snapshot_charts_os.os_cpu_load) — Compare involuntary switches with host run-queue pressure.
- [activity_locks.lock_waits](#item-activity_locks.lock_waits) — Check current lock blocking behind voluntary switches.

## Checklist
- Prefer involuntary switches per CPU second for cross-query comparison.
- Correlate voluntary switching with wait and lock evidence.
- Confirm host CPU quotas and process concurrency before tuning SQL.
- Empty means no non-zero comparable native counters; `unsupported` normally means pg_stat_kcache 2.3+ is unavailable.
