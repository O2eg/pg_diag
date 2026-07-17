# Dirty Buffers By Usage Count

This instruction belongs to report item `buffer_cache.dirty_by_usage_count`.

## What this item shows
- Dirty shared buffers grouped by clock-sweep usage count.
- Cold dirty pages separately from frequently reused dirty pages.

## What to watch
- Sustained low-usage dirty blocks and broad dirty growth.

## Common fault causes
- Burst DML, delayed writeback, or checkpoint pressure.

## Automatic evaluation
- No severity is assigned; a single sample is not diagnostic.

## Related report items
- [buffer_cache.top_dirty_relations](#item-buffer_cache.top_dirty_relations) — Attribute dirty residency to relations.
- [snapshot_delta_workload.background_writer_delta](#item-snapshot_delta_workload.background_writer_delta) — Check background writeback.
- [snapshot_delta_workload.checkpointer_delta](#item-snapshot_delta_workload.checkpointer_delta) — Check checkpoint writeback.

## Checklist
- Review several snapshots.
- Compare with checkpoint, background-writer, and storage-latency items.
