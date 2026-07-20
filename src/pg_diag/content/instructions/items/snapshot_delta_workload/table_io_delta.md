# Table I/O Delta

This instruction belongs to report item `snapshot_delta_workload.table_io_delta`. The item is backed by `objects.table_io_delta` (snapshot metric).

## What this item shows
- Heap/index read deltas, total read/hit deltas, and total block reads/s for stable table OIDs.
- Total counters include heap, indexes, TOAST, and TOAST indexes; labels identify the owning table.
- Up to 200 candidates selected by cumulative total reads, then 50 derived rows.

## What to watch
- High read rate on one relation, heap/index concentration, and TOAST contribution implied by total exceeding displayed heap plus index reads.

## Automatic evaluation
- No severity is assigned because block volume depends on relation size, cache warmth, and workload intent.
- A PostgreSQL block read is a buffer miss/read request; the OS page cache can prevent physical device I/O. Buffer hits are logical accesses, not disk reads.

## Interval coverage
- OID identity, database reset epoch, counter-decrease detection, and bounded churn follow the table delta contract.
- Single-table reset followed by sufficient regrowth can remain undetectable.

## Common fault causes
- Large scans, cold cache, inefficient access paths, TOAST-heavy rows, batch work, or external resets.

## Related report items
- [snapshot_delta_workload.sql_io_delta](#item-snapshot_delta_workload.sql_io_delta) — Attribute statement I/O to table activity.
- [snapshot_charts_os.os_disk_latency](#item-snapshot_charts_os.os_disk_latency) — Check storage latency in the same window.
- [buffer_cache.top_relations](#item-buffer_cache.top_relations) — Inspect the relations occupying shared buffers.

## Checklist
- Compare with statement shared I/O and OS disk latency.
- Inspect relation size, indexes, predicates, and large-value access.
- Do not calculate physical bytes by assuming every block read reached storage.
- Empty means no non-zero comparable bounded candidate.
