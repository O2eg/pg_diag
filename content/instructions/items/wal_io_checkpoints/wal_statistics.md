# WAL Statistics

This instruction belongs to report item `wal_io_checkpoints.wal_statistics`. The item is backed by `wal.stat_wal` (SQL query).

## What this item shows
- Cumulative pg_stat_wal counters for WAL records, FPIs, bytes, writes, syncs, and buffers full.
- WAL generation and write behavior since stats reset.
- Whether WAL path pressure is visible at PostgreSQL level.

## What to watch
- High WAL bytes or records.
- wal_buffers_full increasing.
- High WAL write or sync counts.
- Stats reset before capture.

## Common fault causes
- Write-heavy transactions.
- Small transactions causing frequent WAL sync.
- wal_buffers too small for bursts.
- Checkpoint timing increasing FPIs.

## Checklist
- Compare with WAL growth chart for rate.
- Check archive and replication capacity.
- Review top SQL by WAL for statement source.
