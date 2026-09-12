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
- `stats_window_start` and `stats_window_source` give a lower bound of the counter window: the counters have accumulated at least since that moment. It is the latest of the postmaster start, `pg_stat_database.stats_reset` (exact when set; on PostgreSQL 15+ it stays NULL until `pg_stat_reset()` is called) and the shared statistics reset time (`pg_stat_bgwriter.stats_reset`). A shared reset after the postmaster started is either a crash recovery, which discards every counter, or a targeted `pg_stat_reset_shared()`, which leaves per-object counters older, so the later time never overstates the window; statistics also survive clean restarts, so the true window may be longer than shown. An object created after `stats_window_start` has accumulated only since its creation, which the catalog does not record.

## Related report items
- [snapshot_delta_workload.table_dml_delta](#item-snapshot_delta_workload.table_dml_delta) — Measure current table changes instead of cumulative totals.
- [snapshot_delta_workload.table_scan_delta](#item-snapshot_delta_workload.table_scan_delta) — Measure current table scans.
- [snapshot_charts_db.tables_top_dml_rate](#item-snapshot_charts_db.tables_top_dml_rate) — Inspect write-hot tables over time.

## Checklist
- Check stats_reset before interpreting totals.
- Compare with table delta metrics for current activity.
- Review indexes and autovacuum settings for hot tables.
