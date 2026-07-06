# Table I/O Delta

This instruction belongs to report item `snapshot_delta_workload.table_io_delta`. The item is backed by `objects.table_io_delta` (snapshot metric).

## What this item shows
- Per-table heap, index, toast, and toast-index block I/O deltas during the capture window.
- Object-level read and cache pressure by table.

## What to watch
- High heap block read rate.
- High index block read rate on one table.
- Toast reads from large values.

## Common fault causes
- Large scans.
- Cold cache.
- Inefficient index access.
- TOAST-heavy rows.

## Checklist
- Compare with SQL shared I/O delta.
- Check whether the object is expected to be hot.
- Review indexes and query predicates for hot tables.
