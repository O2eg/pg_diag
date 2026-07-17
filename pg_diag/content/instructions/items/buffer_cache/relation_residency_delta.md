# Relation Cache Residency Delta

This instruction belongs to report item `buffer_cache.relation_residency_delta`.

## What this item shows
- Signed cached-block changes between adjacent snapshots.
- Positive net residency gained and negative net residency lost.

## What to watch
- Repeated losses from important relations or large gains from bulk-accessed objects.

## Common fault causes
- Working-set competition, bulk scans, maintenance, or cache warming.

## Automatic evaluation
- No severity is assigned. This is a gauge difference, not an eviction counter.

## Related report items
- [buffer_cache.top_relations](#item-buffer_cache.top_relations) — Inspect absolute cache residents.
- [snapshot_delta_workload.table_io_delta](#item-snapshot_delta_workload.table_io_delta) — Compare residency changes with relation I/O.
- [snapshot_charts_os.os_disk_read_throughput](#item-snapshot_charts_os.os_disk_read_throughput) — Check host reads during cache churn.

## Checklist
- Do not interpret net change as exact loads or evictions.
- Treat an absent endpoint as unknown, never zero.
