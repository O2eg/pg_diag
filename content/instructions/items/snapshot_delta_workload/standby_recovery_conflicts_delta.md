# Standby Recovery Conflicts Delta

This instruction belongs to report item `snapshot_delta_workload.standby_recovery_conflicts_delta`.

## What this item shows
- Queries cancelled on a standby during the window, split by recovery-conflict reason and database.

## What to watch
- Snapshot conflicts from long reads, lock conflicts during replay, buffer-pin conflicts, and logical-slot conflicts.

## Automatic evaluation
- Any new recovery conflict produces `medium` severity because at least one standby query was cancelled.

## Interval coverage
- Values require matching database identity and unchanged `pg_stat_database.stats_reset`.
- Primary servers normally show zero deltas.

## Common fault causes
- Long standby queries, vacuum cleanup on the primary, DDL replay, pinned buffers, and logical decoding horizons.

## Checklist
- Correlate the conflict category with standby logs and query workload.
- Review feedback or recovery-delay settings only after considering retained-WAL and bloat impact.
