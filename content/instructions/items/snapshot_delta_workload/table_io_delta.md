# Table I/O Delta

This instruction belongs to report item `snapshot_delta_workload.table_io_delta`. The item is backed by `objects.table_io_delta` (snapshot metric).

## What this item shows
- Per-table heap, index, toast, and toast-index block I/O deltas during the capture window.
- Object-level read and cache pressure by table.

## What to watch
- High heap block read rate.
- High index block read rate on one table.
- Toast reads from large values.

## Interval coverage
- The SQL source is sorted and limited before rows enter collector memory.
- Only tables present in both bounded endpoint selections have a calculable delta.
- `missing_start` and `missing_end` are expected selection churn, not zero activity or errors.
- Counter decreases or invalid values are omitted and reported as invalid coverage.

## Common fault causes
- Large scans.
- Cold cache.
- Inefficient index access.
- TOAST-heavy rows.

## Checklist
- Compare with SQL shared I/O delta.
- Check whether the object is expected to be hot.
- Review indexes and query predicates for hot tables.
