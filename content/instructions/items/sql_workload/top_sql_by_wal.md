# Top SQL By WAL Generated

This instruction belongs to report item `sql_workload.top_sql_by_wal`. The item is backed by `statements.top_by_wal` (SQL query).

## What this item shows
- Statements ranked by WAL bytes, WAL records, and full-page images.
- SQL responsible for write-ahead-log volume.
- Write amplification candidates among normalized statements.

## What to watch
- One statement dominating WAL bytes.
- High full-page images after checkpoints.
- Unexpected WAL from statements that should affect few rows.

## Common fault causes
- Bulk insert/update/delete.
- Frequent updates to indexed columns.
- Large transactions.
- Checkpoint timing increasing full-page writes.

## Checklist
- Compare WAL-heavy SQL with table DML delta.
- Check whether batching or index changes can reduce WAL.
- Ensure archive/replication capacity can handle the WAL rate.
