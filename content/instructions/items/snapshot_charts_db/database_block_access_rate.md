# Database Block Access Rate

This instruction belongs to report item `snapshot_charts_db.database_block_access_rate`. The item is backed by `database.block_access_rate` (snapshot metric).

## What this item shows
- Database block hit and read rates over time.
- Buffer cache activity and physical-read pressure.

## What to watch
- Read rate increasing while hit rate falls.
- Physical reads aligned with disk latency.
- Block activity spike after cache cold start.

## Common fault causes
- Working set larger than memory.
- Large scans.
- Restart/cold cache.
- Plan change.

## Automatic evaluation
- Read and buffer-hit deltas are distinct block access outcomes and are stacked for the connected database.
- pg_diag's own catalog reads contribute observer overhead; use object/SQL I/O deltas for attribution.

## Checklist
- Compare with SQL shared I/O and table I/O.
- Use OS disk read charts for storage impact.
- Check cache warmup after restart.
