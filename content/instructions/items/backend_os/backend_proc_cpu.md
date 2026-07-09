# PostgreSQL Backend /proc CPU

This instruction belongs to report item `backend_os.backend_proc_cpu`. The item is backed by `backend.proc_cpu_top` (window-endpoint metric).

## What this item shows
- Average CPU use per local PostgreSQL process over the snapshots window.
- The rate is calculated from two `/proc/<pid>/stat` counter reads: one at window start and one at window end.
- Only a process with the same PID and process start time at both endpoints can be included.

## What to watch
- One PID using most CPU over the full window.
- Parallel workers consuming CPU as a group.
- An empty result when PostgreSQL processes started or exited inside the window, or `/proc` is unavailable.

## Common fault causes
- CPU-bound query.
- Parallel plan.
- Autovacuum or maintenance job.
- Collector permission limits.

## Checklist
- Use the PID and command to correlate with Backend Activity; this item does not contain a query ID.
- Group leader and parallel worker PIDs together.
- Treat the value as a window average, not a peak measurement.
- Run pg_diag locally with permissions required for `/proc` access.
