# Table Scan Delta

This instruction belongs to report item `snapshot_delta_workload.table_scan_delta`. The item is backed by `objects.table_scan_delta` (snapshot metric).

## What this item shows
- Per-table sequential scan and index scan deltas during the capture window.
- Tables currently scanned by sequential or index access.

## What to watch
- High sequential scan rate on large tables.
- Index scan rate collapse after release.
- Rows read per scan much higher than expected.

## Common fault causes
- Missing index.
- Planner estimate drift.
- Reporting query.
- Small table intentionally scanned.

## Checklist
- Check table size before treating seq scans as bad.
- Review top SQL plans.
- Run ANALYZE if stats are stale.
