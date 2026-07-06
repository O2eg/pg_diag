# Table Workload Counters

This instruction belongs to report item `object_workload.table_workload`. The item is backed by `objects.table_workload` (SQL query).

## What this item shows
- Cumulative table scans, tuple reads, DML, vacuum, and analyze counters.
- Per-table activity since stats reset.
- Hot tables by read/write and maintenance activity.

## What to watch
- High sequential scans on large tables.
- High updates/deletes with stale vacuum/analyze activity.
- Tables with many rows read but few rows changed.

## Common fault causes
- Missing index.
- Stale statistics.
- Hot OLTP table.
- Batch/report scan.

## Checklist
- Check stats_reset before interpreting totals.
- Compare with table delta metrics for current activity.
- Review indexes and autovacuum settings for hot tables.
