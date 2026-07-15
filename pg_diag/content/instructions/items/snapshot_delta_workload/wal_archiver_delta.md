# WAL Archiver Delta

This instruction belongs to report item `snapshot_delta_workload.wal_archiver_delta`.

## What this item shows
- WAL segments archived successfully and archive attempts that failed during the window.
- The last successful and failed WAL names observed at the finish endpoint.

## What to watch
- Any failed attempt, no successful progress while WAL is generated, and divergence between generation and archival rates.

## Automatic evaluation
- New archive failures produce `medium` severity.

## Interval coverage
- Values require unchanged `pg_stat_archiver.stats_reset`.

## Common fault causes
- Unavailable archive targets, permissions, capacity, command errors, network loss, and slow archival.

## Checklist
- Inspect archiver logs and target health.
- Compare archive progress with WAL Activity Delta and pending-segment evidence.
