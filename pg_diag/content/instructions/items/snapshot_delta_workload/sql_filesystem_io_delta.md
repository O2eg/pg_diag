# SQL Filesystem I/O Delta

This instruction belongs to report item `snapshot_delta_workload.sql_filesystem_io_delta`. The item is backed by `statements.filesystem_io_delta` (snapshot metric).

## What this item shows
- `pg_stat_kcache` execution reads/writes as byte deltas, bytes per second, and bytes per call for each SQL identity.
- `B/s` is filesystem-counter bytes per wall-clock second; these are kernel/getrusage counters, not PostgreSQL shared-buffer blocks and not guaranteed durable-device bytes.
- Up to 50 comparable rows from an independent 250-entry endpoint candidate set; `query_id` opens captured SQL text.

## What to watch
- High read or write rates aligned with device throughput, latency, or cache churn.
- Large bytes per call, which distinguishes heavy individual executions from high-frequency small I/O.
- Null or absent platform counters; zero is meaningful only when capability and interval coverage are valid.

## Automatic evaluation
- No universal byte-rate threshold is assigned because storage capacity and workload expectations differ.
- Unsupported native counters are omitted rather than interpreted as zero activity.

## Interval coverage
- The same query identity and unchanged `pg_stat_kcache.stats_since` are required at both window endpoints.
- Missing candidates and reset/decreased counters are reported in coverage and omitted from the ranking.

## Common fault causes
- Working sets larger than shared buffers or OS page cache.
- Sequential scans, temporary files, relation extension, checkpoints, or direct filesystem work performed by extensions.
- Cold cache after restart or cache displacement by another workload.

## Related report items
- [snapshot_delta_workload.sql_io_attribution_delta](#item-snapshot_delta_workload.sql_io_attribution_delta) — Compare filesystem bytes with PostgreSQL block counters.
- [snapshot_delta_workload.sql_io_delta](#item-snapshot_delta_workload.sql_io_delta) — Inspect shared-block reads, writes, and I/O timing for the same SQL.
- [snapshot_charts_db.database_filesystem_io_rate](#item-snapshot_charts_db.database_filesystem_io_rate) — Correlate statement bytes with the database timeline.
- [snapshot_charts_os.os_disk_read_throughput](#item-snapshot_charts_os.os_disk_read_throughput) — Compare attributed reads with host devices.

## Checklist
- Confirm pg_stat_kcache 2.3+ and comparable entry epochs.
- Separate reads from writes and rate from bytes per call.
- Correlate timestamps with OS disk latency and throughput; counters at different layers need not match exactly.
- Empty means no non-zero comparable candidate; `unsupported` normally means the extension/API or native counters are unavailable.
