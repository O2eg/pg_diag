# SQL WAL Delta

This instruction belongs to report item `snapshot_delta_workload.sql_wal_delta`. The item is backed by `statements.wal_delta` (snapshot metric).

## What this item shows
- Per-statement WAL byte, record, and FPI deltas during the capture window.
- Which SQL generated WAL while snapshots were running.

## What to watch
- High WAL bytes per second.
- High full-page-image rate.
- WAL-heavy SQL during replication lag.

## Common fault causes
- Bulk writes.
- Checkpoint interaction.
- Indexed-column updates.
- Large transactions.

## Checklist
- Compare with WAL growth chart.
- Check archive and replication capacity.
- Review whether write batching is possible.
