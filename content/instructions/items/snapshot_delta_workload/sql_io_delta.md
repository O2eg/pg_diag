# SQL Shared I/O Delta

This instruction belongs to report item `snapshot_delta_workload.sql_io_delta`. The item is backed by `statements.io_delta` (snapshot metric).

## What this item shows
- Per-statement shared block I/O changes during the snapshot window.
- Which SQL read or wrote shared buffers during this capture.

## What to watch
- High shared block read/write rate.
- I/O delta from SQL not prominent in cumulative table.
- Sudden write-heavy statement.

## Common fault causes
- Batch scan.
- Cache miss burst.
- Bulk update/delete.
- Plan change.

## Checklist
- Compare with OS disk read/write charts.
- Review BUFFERS in EXPLAIN.
- Check table_io_delta for object targets.
