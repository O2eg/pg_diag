# Dirty And Pinned Buffers

This instruction belongs to report item `buffer_cache.dirty_and_pinned`.

## What this item shows
- Dirty buffers and buffers pinned by one or more backends.
- Two overlapping gauges that must not be summed.

## Units
- `blocks` counts dirty or pinned shared-buffer slots/pages. One block uses the server's configured `block_size`; `kblocks` and `Mblocks` are SI-scaled block counts.

## What to watch
- Sustained dirty growth or prolonged pinned-buffer growth.

## Common fault causes
- Heavy DML, slow writeback, or checkpoint pressure.
- Long-running operations holding buffer pins.

## Automatic evaluation
- No severity is assigned because workload and pool size determine acceptable levels.

## Related report items
- [buffer_cache.top_dirty_relations](#item-buffer_cache.top_dirty_relations) — Identify relations contributing dirty buffers.
- [snapshot_delta_workload.checkpointer_delta](#item-snapshot_delta_workload.checkpointer_delta) — Check checkpoint writeback.
- [activity_locks.wait_events](#item-activity_locks.wait_events) — Look for buffer-pin and I/O waits.

## Checklist
- Correlate with sessions, waits, checkpoints, and PostgreSQL I/O.
- Do not add the two lines; a buffer can be both dirty and pinned.
