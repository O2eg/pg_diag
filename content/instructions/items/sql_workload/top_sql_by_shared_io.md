# Top SQL By Shared Block I/O

This instruction belongs to report item `sql_workload.top_sql_by_shared_io`. The item is backed by `statements.top_by_io` (SQL query).

## What this item shows
- Statements ranked by shared block reads plus writes.
- Which SQL drives buffer cache misses or shared-buffer write activity.
- Block hit/read/dirtied/written counters for normalized statements.

## What to watch
- High shared_blks_read relative to calls.
- High dirtied or written blocks for statements expected to be read-only.
- I/O-heavy SQL with low execution time but high system impact.

## Common fault causes
- Large scans.
- Missing or ineffective indexes.
- Cold cache.
- Write-heavy plans or bulk updates.

## Checklist
- Review plans with BUFFERS output.
- Check whether reads are expected batch/report traffic.
- Compare with table I/O and OS disk charts.
