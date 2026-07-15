# Top SQL By WAL Generated

This instruction belongs to report item `sql_workload.top_sql_by_wal`. The item is backed by `statements.top_by_wal` (SQL query).

## What this item shows
- Up to 50 current-database entries ranked by cumulative WAL bytes generated.
- WAL records, full-page images, calls, execution time, rows, statement identity, and representative SQL. WAL counters are available from PostgreSQL 13.
- PostgreSQL 13 has no `toplevel` field; `stats_since` exists on PostgreSQL 17+ and is unavailable on PostgreSQL 13-16.

## What to watch
- WAL bytes per call and per affected row, not only the cumulative total.
- High full-page-image volume correlated with checkpoints.
- Unexpected WAL from a statement believed to be read-only or narrowly updating rows.

## Automatic evaluation
- WAL volume does not assign severity because write workload and retention capacity are deployment-specific.
- `unknown` indicates hidden statement identity for at least one row.
- This is cumulative generated WAL, not a capture-window rate and not proof of archive or replication lag.

## Common fault causes
- Bulk insert/update/delete, updates to indexed columns, large transactions, or full-page writes after checkpoints.
- Legitimate write-heavy workload retained over a long statistics window.
- Entry churn hiding part of the historical workload.

## Checklist
- Establish entry/reset age and divide WAL by calls/rows before comparing statements.
- Correlate with interval WAL growth, checkpoint, archive, and replication evidence.
- Review schema/index write amplification before changing durability settings.
- Empty/unsupported semantics follow the capability item; collection is one-shot and bounded to 50 rows.
