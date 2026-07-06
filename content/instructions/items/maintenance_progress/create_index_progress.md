# Create Index Progress

This instruction belongs to report item `maintenance_progress.create_index_progress`. The item is backed by `progress.create_index` (SQL query).

## What this item shows
- Live progress rows for CREATE INDEX or REINDEX operations.
- Build phase, blocks, tuples, lockers, and partition progress where available.
- Which index build is currently active.

## What to watch
- Long validation or waiting phase.
- Concurrent index build holding resources.
- Index build on large table during peak workload.

## Common fault causes
- Large table.
- Insufficient maintenance_work_mem.
- Lockers delaying phase.
- Slow I/O.

## Checklist
- Check lock waiters and blockers.
- Confirm whether build is concurrent.
- Schedule heavy builds outside peak hours when possible.
