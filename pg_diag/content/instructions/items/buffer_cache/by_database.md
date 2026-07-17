# Buffer Cache By Database

This instruction belongs to report item `buffer_cache.by_database`.

## What this item shows
- Cached blocks attributed to every cluster database and shared catalogs.
- Cluster-wide shared-buffer composition by database.

## What to watch
- A database rapidly displacing the established cache composition.

## Common fault causes
- Bulk scans, maintenance, or a workload shift in one database.

## Automatic evaluation
- No severity is assigned. Occupancy is not workload rate.

## Related report items
- [buffer_cache.utilization](#item-buffer_cache.utilization) — Include unused buffers omitted from database attribution.
- [overview.database_stats](#item-overview.database_stats) — Compare cache occupancy with database activity.
- [snapshot_charts_db.database_block_access_rate](#item-snapshot_charts_db.database_block_access_rate) — Compare occupancy with block rates.

## Checklist
- Use Buffer Cache Utilization for unused buffers, which are excluded here.
- Correlate changes with per-database workload and I/O charts.
