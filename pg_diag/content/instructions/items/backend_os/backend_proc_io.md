# PostgreSQL Backend /proc I/O

This instruction belongs to report item `backend_os.backend_proc_io`. The item is backed by `backend.proc_io_top` (window-endpoint metric).

## What this item shows
- Average read/write rates per local PostgreSQL process over the snapshots window.
- The rates are calculated from two `/proc/<pid>/io` counter reads: one at window start and one at window end.
- Only a process with the same PID and process start time at both endpoints can be included.

## What to watch
- One backend producing most reads or writes over the full window.
- Null rates with `io_access=false`; these mean that the counters were not readable, not that I/O was zero.
- Missing short-lived backends that started or exited inside the window.

## Common fault causes
- I/O-heavy query.
- COPY or maintenance operation.
- Autovacuum.
- Collector lacks permission to read /proc/<pid>/io.

## Automatic evaluation
- This item is informational; expected throughput depends on workload and storage.
- Rates remain null unless `/proc/<pid>/io` was readable at both endpoints; `io_access=false` is not converted into zero activity.
- PID reuse is rejected by matching process start time.

## Checklist
- Check `io_access` before interpreting the rates.
- Use the PID and command to correlate with Backend Activity and SQL text.
- Treat the rates as window averages, not peak measurements.
- Compare with pg_stat_io and OS disk charts.
