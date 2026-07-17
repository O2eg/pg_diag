# Cluster Progress

This instruction belongs to report item `maintenance_progress.cluster_progress`. The item is backed by `progress.cluster` (SQL query).

## What this item shows
- A one-time, current-database snapshot of CLUSTER and VACUUM FULL operations visible when the report starts.
- Command, table/index OIDs and names, state/wait, rewrite phase, scanned blocks/bytes, tuples, rebuilt indexes, and full command age.
- The index is null/zero when VACUUM FULL or a non-index scan does not use a clustering index.

## What to watch
- Lock impact, repeated phase/counter stagnation, high rewrite I/O, and temporary disk-space consumption.
- Scan percentage only during the sequential-scan phase; other phases use tuple or index-rebuild counters and do not share one overall percentage.

## Automatic evaluation
- No automatic severity: CLUSTER/VACUUM FULL is intentionally invasive, but whether its timing and lock impact are acceptable is deployment-specific.

## Common fault causes
- Large relation, insufficient free space, slow storage, index rebuild cost, lock contention, or maintenance scheduled during traffic.

## Related report items
- [activity_locks.lock_waits](#item-activity_locks.lock_waits) — Check locks around the clustered relation.
- [snapshot_charts_os.os_disk_read_throughput](#item-snapshot_charts_os.os_disk_read_throughput) — Inspect read throughput during table rewrite.
- [snapshot_charts_os.os_disk_write_throughput](#item-snapshot_charts_os.os_disk_write_throughput) — Inspect write throughput during table rewrite.

## Checklist
- Verify command owner, expected maintenance window, blocking sessions, and free disk space before intervention.
- Compare later captures by PID/relation and phase; do not extrapolate completion time from one phase percentage.
- Remember VACUUM FULL is reported here, not in Vacuum Progress.
- Empty means no visible current-database CLUSTER or VACUUM FULL was active at capture time.
