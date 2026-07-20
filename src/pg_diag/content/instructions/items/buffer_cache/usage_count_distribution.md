# Buffer Usage Count Distribution

This instruction belongs to report item `buffer_cache.usage_count_distribution`.

## What this item shows
- Buffer counts at each clock-sweep usage count from 0 through 5.
- How strongly cached pages have recently been reused.

## Units
- `blocks` counts shared-buffer slots/pages in each usage-count group. One block uses the server's configured `block_size`; `kblocks` and `Mblocks` are SI-scaled block counts.

## What to watch
- Growth in usage counts 0 and 1 alongside physical reads.
- Material shifts in the distribution during workload changes.

## Common fault causes
- One-pass scans or a working set larger than shared buffers.
- A newly warmed or recently restarted server.

## Automatic evaluation
- No severity is assigned; this is not a hit ratio.

## Related report items
- [buffer_cache.top_relations](#item-buffer_cache.top_relations) — Identify relations occupying the cache.
- [snapshot_charts_db.database_block_access_rate](#item-snapshot_charts_db.database_block_access_rate) — Compare usage counts with block activity.

## Checklist
- Interpret the distribution over time and alongside physical reads.
- Use relation charts to identify which objects occupy the cache.
