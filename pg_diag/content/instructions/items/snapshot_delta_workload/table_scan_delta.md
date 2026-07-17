# Table Scan Delta

This instruction belongs to report item `snapshot_delta_workload.table_scan_delta`. The item is backed by `objects.table_scan_delta` (snapshot metric).

## What this item shows
- Sequential scan/tuple-read and index scan/tuple-fetch deltas for stable table OIDs.
- Sequential scans/s and sequential tuples read/s during the actual endpoint interval.
- Up to 200 candidates selected by cumulative sequential tuples read, then 50 derived rows.

## What to watch
- Sustained sequential scans and tuple reads on relations not intentionally scanned.
- High sequential tuple reads with little index activity, interpreted with table size and workload purpose.

## Automatic evaluation
- `medium`: at least 10 sequential scans/s and 10000 sequential tuples read/s for the same relation.
- The dual threshold avoids classifying a few large scans or many scans of a tiny table from only one signal. It is a review prompt, not an instruction to create an index.

## Interval coverage
- `(datid, relid)` identity, database reset epoch, counter decreases, and bounded-selection behavior match `Table DML Delta`.
- Single-table resets that regrow beyond the starting value cannot be proven because PostgreSQL exposes no per-table reset timestamp.

## Common fault causes
- Missing/ineffective index, low-selectivity predicate, deliberate batch scan, small lookup table, or reset/selection churn.

## Related report items
- [snapshot_delta_workload.table_io_delta](#item-snapshot_delta_workload.table_io_delta) — Check block I/O for heavily scanned tables.
- [snapshot_delta_workload.sql_time_delta](#item-snapshot_delta_workload.sql_time_delta) — Find SQL active during the same window.
- [indexes.foreign_keys_without_index](#item-indexes.foreign_keys_without_index) — Review one source of repeated table scans.

## Checklist
- Check relation size, cache behavior, query predicates, and representative plans.
- Do not create an index from this summary alone.
- Correlate with SQL time/I/O and table I/O deltas.
- Empty means no non-zero comparable candidate, not proof that no scans occurred outside the bounded set.
