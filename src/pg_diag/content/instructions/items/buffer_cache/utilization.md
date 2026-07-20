# Buffer Cache Utilization

This instruction belongs to report item `buffer_cache.utilization`.

## What this item shows
- Used and unused PostgreSQL shared-buffer slots at each snapshot.
- The occupancy trend of the configured shared-buffer pool.

## Units
- `blocks` counts shared-buffer slots/pages. One block uses the server's configured `block_size`; large values may be displayed with SI prefixes such as `kblocks` or `Mblocks`.

## What to watch
- Abrupt changes after restart, failover, or workload shifts.
- Occupancy changes that coincide with physical-read growth.

## Common fault causes
- A changed working set or bulk scan.
- Restart or failover warming an initially empty cache.

## Automatic evaluation
- No severity is assigned. A persistently full cache is normal under active workload.
- A red error block means `pg_buffercache` could not be queried.

## Related report items
- [buffer_cache.usage_count_distribution](#item-buffer_cache.usage_count_distribution) — Inspect recency distribution inside used buffers.
- [snapshot_charts_db.database_block_access_rate](#item-snapshot_charts_db.database_block_access_rate) — Compare occupancy with block-hit and read rates.
- [snapshot_charts_os.os_disk_read_throughput](#item-snapshot_charts_os.os_disk_read_throughput) — Check physical reads during cache changes.

## Checklist
- Correlate with cache churn and read I/O.
- Install or grant access to `pg_buffercache` only under the site's change procedure.
- Treat the one-second SQL timeout as best-effort on PostgreSQL 10-12 and on
  PostgreSQL releases older than 13.23, 14.20, 15.15, 16.11, 17.7, or 18.1.
  Their `pg_buffercache` loops can finish scanning shared buffers before they
  observe cancellation. Prefer a patched minor release on large buffer pools.
