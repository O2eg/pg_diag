# Top Tables By Heap Block Read Rate

This instruction belongs to report item `snapshot_charts_db.tables_top_heap_read_rate`. The item is backed by `objects.tables_top_heap_read_rate` (snapshot metric).

## What this item shows
- Tables with highest heap block read rate.
- Current physical heap-read pressure by table.

## What to watch
- Large heap reads from one relation.
- Reads aligned with disk latency.
- Heap reads on table expected to be cached.

## Common fault causes
- Sequential scan.
- Cold cache.
- Working set too large.
- Plan change.

## Checklist
- Review SQL touching top tables.
- Compare with OS disk reads.
- Check indexes and table statistics.
