# Create Index Progress

This instruction belongs to report item `maintenance_progress.create_index_progress`. The item is backed by `progress.create_index` (SQL query).

## What this item shows
- A one-time, current-database snapshot of CREATE INDEX and REINDEX operations visible when the report starts.
- Command type, database/table/index OIDs and names, phase, current locker, phase-specific blocks/tuples/partitions, wait state, and full command age.
- Index OID/name can be null during non-concurrent CREATE INDEX before PostgreSQL assigns the final relation.

## What to watch
- Waiting phases with a `current_locker_pid`, repeated captures without phase/counter movement, or heavy I/O during build/validation.
- Whether the command is concurrent; non-concurrent builds intentionally block writes, while concurrent builds use additional scans and wait phases.
- Percentages only when the corresponding total is non-zero and valid for the current phase.

## Automatic evaluation
- No automatic severity: waiting is part of normal concurrent-index protocol and a single capture cannot distinguish brief coordination from a stall.

## Common fault causes
- Large table/index, slow storage, low maintenance memory, long transactions or old snapshots, lock contention, and partition fan-out.

## Checklist
- Resolve `current_locker_pid` through Activity & Locks before cancelling either backend.
- Compare later captures by PID/command and phase; counters can reset when the phase changes.
- Confirm build type and index validity before retrying or dropping artifacts.
- Empty means no visible current-database CREATE INDEX or REINDEX was active at capture time.
