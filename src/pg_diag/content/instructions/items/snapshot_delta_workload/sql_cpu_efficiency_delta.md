# SQL CPU Efficiency Delta

This instruction belongs to report item `snapshot_delta_workload.sql_cpu_efficiency_delta`. The item is backed by `statements.cpu_efficiency_delta` (snapshot metric).

## What this item shows
- Calls/s, CPU seconds/s, CPU milliseconds per call, execution milliseconds per call, CPU/elapsed percent, and user/system CPU shares.
- `CPU-s/s = 1.0` is one occupied logical CPU; `ms/call` divides interval deltas, and percentages are ratios of comparable interval deltas.
- `query_id` opens the SQL captured from `pg_stat_statements`; the table returns up to 50 rows from its own 250-entry candidate set.

## What to watch
- CPU/elapsed near 100% for serial CPU-bound work; it may exceed 100% with parallel or overlapping CPU accounted to the statement.
- Low CPU/elapsed with high execution time, suggesting waits, locks, I/O, or client-facing delay rather than computation.
- High system share or CPU per call after a plan or data-volume change.

## Automatic evaluation
- No fixed efficiency threshold is assigned because parallelism and wait composition vary by workload.
- Ratios are absent when the interval has no calls/elapsed activity or any required counter reset/decreased.

## Interval coverage
- CPU, calls, elapsed time, identity, and the `pg_stat_kcache.stats_since` epoch must be comparable at both endpoints.
- Entry/candidate churn is omitted; ratios use only deltas from the same accepted interval.

## Common fault causes
- CPU-heavy plans, JIT, expression evaluation, sorting, hashing, or compression.
- Lock, I/O, remote-call, or synchronization waits lowering CPU/elapsed.
- Query entry churn, reset, or endpoint Top-N membership changes.

## Related report items
- [snapshot_delta_workload.sql_kernel_cpu_delta](#item-snapshot_delta_workload.sql_kernel_cpu_delta) — Inspect absolute user/system CPU deltas.
- [snapshot_delta_workload.sql_time_delta](#item-snapshot_delta_workload.sql_time_delta) — Compare execution-time and call deltas independently.
- [snapshot_delta_workload.sql_context_switches_delta](#item-snapshot_delta_workload.sql_context_switches_delta) — Check scheduling overhead for inefficient rows.
- [activity_locks.wait_event_sample_profile](#item-activity_locks.wait_event_sample_profile) — Identify sampled waits when elapsed time exceeds CPU time.

## Checklist
- Interpret CPU/elapsed with statement parallelism and concurrency in mind.
- Compare per-call and per-second values before deciding whether frequency or individual cost dominates.
- Use the same query identity across CPU, time, wait, and I/O items.
- Empty means no non-zero comparable candidate; `unsupported` normally means a pg_stat_kcache prerequisite is missing.
