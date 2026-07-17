# Buffer Cache Utilization

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

## Checklist
- Correlate with cache churn and read I/O.
- Install or grant access to `pg_buffercache` only under the site's change procedure.
