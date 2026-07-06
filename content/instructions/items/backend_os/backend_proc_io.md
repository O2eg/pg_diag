# PostgreSQL Backend /proc I/O

This instruction belongs to report item `backend_os.backend_proc_io`. The item is backed by `backend.proc_io_top` (snapshot metric).

## What this item shows
- Per-PostgreSQL-process read/write rates sampled from local /proc I/O counters.
- Which backend PIDs generated local process I/O during snapshots mode.
- OS-level I/O attribution by backend when permissions allow it.

## What to watch
- One backend producing most reads or writes.
- Zero values with io_access=false.
- High write rate from maintenance or bulk load PID.

## Common fault causes
- I/O-heavy query.
- COPY or maintenance operation.
- Autovacuum.
- Collector lacks permission to read /proc/<pid>/io.

## Checklist
- Check io_access before trusting zeros.
- Map PID to Backend Activity and SQL text.
- Compare with pg_stat_io and OS disk charts.
