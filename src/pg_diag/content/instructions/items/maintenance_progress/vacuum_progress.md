# Vacuum Progress

This instruction belongs to report item `maintenance_progress.vacuum_progress`. The item is backed by `progress.vacuum` (SQL query).

## What this item shows
- A one-time, current-database snapshot of regular VACUUM and autovacuum rows visible in `pg_stat_progress_vacuum` when the report starts.
- Database/relation OIDs and names, backend/mode, state/wait, phase, heap scan/vacuum progress, index cycles, command age, and bounded query text.
- PostgreSQL 10-16 dead-tuple item counts versus PostgreSQL 17+ byte/item/index progress fields.

## What to watch
- A wait event, repeated captures stuck in the same phase/counter position, multiple index-vacuum cycles, or an anti-wraparound autovacuum.
- Heap scan percentage as scan progress only; heap-vacuum percentage advances in different phases and can jump over pages without dead tuples.
- High I/O or lock impact in the surrounding workload, not merely the presence of maintenance.

## Automatic evaluation
- No automatic severity: an active VACUUM or autovacuum is normally healthy maintenance, and one point-in-time row cannot prove it is stalled.
- `anti_wraparound` is null when autovacuum query text is hidden, rather than guessed from backend XID state.

## Common fault causes
- Large/bloated relation, index cleanup cycles, insufficient maintenance memory, cost delay, storage pressure, or a lock wait during truncation.
- Emergency anti-wraparound work caused by an old frozen-XID horizon.

## Related report items
- [storage_vacuum.autovacuum_queue](#item-storage_vacuum.autovacuum_queue) — Check queued tables and worker pressure.
- [storage_vacuum.xmin_horizon_blockers](#item-storage_vacuum.xmin_horizon_blockers) — Find sessions or slots preventing cleanup.
- [snapshot_delta_workload.table_maintenance_delta](#item-snapshot_delta_workload.table_maintenance_delta) — Measure maintenance progress across the window.

## Checklist
- Compare a later capture using the same PID/relation and phase before calling the operation stalled.
- Treat anti-wraparound vacuum as safety-critical; do not cancel it without proving a safer recovery path.
- Correlate with table size, autovacuum eligibility, locks, XID horizons, and OS I/O.
- Empty means no visible current-database regular VACUUM at capture time; VACUUM FULL appears in Cluster Progress.
