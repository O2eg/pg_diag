# Index Usage Delta

This instruction belongs to report item `snapshot_delta_workload.index_usage_delta`. The item is backed by `objects.index_usage_delta` (snapshot metric).

## What this item shows
- Index scans, index entries returned, live table rows fetched, index block reads/hits, and scans/s for stable index OIDs.
- Current table/index labels with `(datid, indexrelid)` identity.
- Up to 200 indexes selected by cumulative scans, then 50 derived rows.

## What to watch
- High index entries read per scan, low table fetches relative to entries, and high block reads during the window.
- Bitmap scans and index-only scans before interpreting `idx_tup_fetch`; index and table view semantics differ by scan type.

## Automatic evaluation
- No severity is assigned. High or low ratios depend on selectivity, scan type, cache state, and query purpose.
- This item proves recent activity for comparable candidates; it cannot prove an index is safe to drop when absent.

## Interval coverage
- Database-wide reset epoch and counter decreases are checked; single-index resets have no exposed timestamp.
- OID identity prevents overload/name collisions and survives renames.
- Top-200 membership changes are informational unmatched coverage.

## Common fault causes
- Low-selectivity index, bitmap or index-only plans, batch/report traffic, cold cache, or reset/selection churn.

## Related report items
- [object_workload.index_workload](#item-object_workload.index_workload) — Compare interval index activity with cumulative counters.
- [indexes.unused_indexes](#item-indexes.unused_indexes) — Avoid treating an index as unused based on one window alone.
- [snapshot_charts_db.indexes_top_scan_rate](#item-snapshot_charts_db.indexes_top_scan_rate) — Inspect the scan-rate ranking over time.

## Checklist
- Review actual plans and the index definition before drawing efficiency conclusions.
- Compare block reads with table/SQL I/O and OS evidence.
- Never drop an index based only on absence from this bounded window.
- Empty means no non-zero comparable candidate.
