# Copy Progress

This instruction belongs to report item `maintenance_progress.copy_progress`. The item is backed by `progress.copy` (SQL query).

## What this item shows
- Live progress for COPY operations.
- Bytes and tuples processed for active COPY commands.
- Which backend is doing bulk load or unload work.

## What to watch
- COPY running longer than expected.
- Low throughput.
- COPY overlapping with WAL, disk, or replication pressure.

## Common fault causes
- Slow client or network.
- Constraint/index overhead.
- WAL/archive bottleneck.
- Large file or transformation cost.

## Checklist
- Identify COPY direction and target relation.
- Check client/network and disk throughput.
- Consider staging or batching for large loads.
