# Backend Activity By PID

This instruction belongs to report item `backend_os.backend_activity`. The item is backed by `backend.activity` (SQL query).

## What this item shows
- Current pg_stat_activity rows with backend type, PID, state, wait event, query_id, and query text.
- Database-side context for per-backend OS CPU and I/O metrics.
- Which PostgreSQL processes were active during local collection.

## What to watch
- Active backend with long query_age.
- Parallel workers tied to one query_id.
- Autovacuum or maintenance backend during workload.

## Common fault causes
- Long query.
- Parallel query.
- Autovacuum.
- Blocked backend.
- Client backend running batch job.

## Checklist
- Map PID to backend_proc_cpu and backend_proc_io items.
- Use query_id to connect backend activity to Top SQL.
- Act on owning query/application, not only the PID.
