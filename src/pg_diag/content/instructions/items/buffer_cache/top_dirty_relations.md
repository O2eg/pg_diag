# Top Dirty Relations In Buffer Cache

This instruction belongs to report item `buffer_cache.top_dirty_relations`.

## What this item shows
- The 30 current-database relations with the most dirty blocks plus `Other`.
- Dirty-cache composition with independent membership per snapshot.

## What to watch
- Sustained dirty residency concentrated in a few relations.

## Common fault causes
- Heavy DML, delayed writeback, or checkpoint activity.

## Automatic evaluation
- No severity is assigned; dirty occupancy alone does not prove a bottleneck.

## Related report items
- [snapshot_delta_workload.table_dml_delta](#item-snapshot_delta_workload.table_dml_delta) — Check write activity on dirty relations.
- [snapshot_delta_workload.checkpointer_delta](#item-snapshot_delta_workload.checkpointer_delta) — Inspect checkpoint writeback.
- [snapshot_charts_os.os_disk_latency](#item-snapshot_charts_os.os_disk_latency) — Check storage latency during dirty-buffer pressure.

## Checklist
- Correlate with DML, checkpoints, writeback, and storage latency.
- Treat `Other` as the bounded remainder.
