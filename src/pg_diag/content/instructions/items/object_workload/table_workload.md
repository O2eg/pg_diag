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

## Automatic evaluation
- `medium` is raised only when both cumulative sequential scans and tuples read are high.
- The threshold is a review signal, not proof that an index is missing; use the delta item and query plans.
- The query takes a bounded top 200 by cumulative DML before calculating exact relation sizes.

## Related report items
- [snapshot_delta_workload.table_dml_delta](#item-snapshot_delta_workload.table_dml_delta) — Measure current table changes instead of cumulative totals.
- [snapshot_delta_workload.table_scan_delta](#item-snapshot_delta_workload.table_scan_delta) — Measure current table scans.
- [snapshot_charts_db.tables_top_dml_rate](#item-snapshot_charts_db.tables_top_dml_rate) — Inspect write-hot tables over time.

## Checklist
- Check stats_reset before interpreting totals.
- Compare with table delta metrics for current activity.
- Review indexes and autovacuum settings for hot tables.
