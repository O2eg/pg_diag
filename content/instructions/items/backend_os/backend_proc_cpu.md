# PostgreSQL Backend /proc CPU

This instruction belongs to report item `backend_os.backend_proc_cpu`. The item is backed by `backend.proc_cpu_top` (snapshot metric).

## What this item shows
- Per-PostgreSQL-process CPU rate sampled from local /proc data.
- Which backend PIDs consumed CPU during snapshots mode.
- CPU hotspots correlated with pg_stat_activity.

## What to watch
- One PID or query_id using most CPU.
- Parallel workers consuming CPU as a group.
- Missing data because collector cannot read /proc.

## Common fault causes
- CPU-bound query.
- Parallel plan.
- Autovacuum or maintenance job.
- Collector permission limits.

## Checklist
- Map PID back to Backend Activity.
- Group leader and parallel worker PIDs together.
- Run collector with permissions required for /proc sampling.
