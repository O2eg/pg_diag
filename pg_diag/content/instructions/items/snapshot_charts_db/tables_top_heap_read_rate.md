# Top Tables By Heap Block Read Rate

This instruction belongs to report item `snapshot_charts_db.tables_top_heap_read_rate`. The item is backed by `objects.tables_top_heap_read_rate` (snapshot metric).

## What this item shows
- Tables with highest heap block read rate.
- Current physical heap-read pressure by table.

## What to watch
- Large heap reads from one relation.
- Reads aligned with disk latency.
- Heap reads on table expected to be cached.

## Bounded samples
- Each SQL sample is ordered and limited before rows enter collector memory.
- Each column ranks deltas only for keys present in both adjacent bounded samples.
- Different table series between columns are expected; unmatched keys are not zero or errors.
- Counter decreases and invalid values are omitted and reported separately.

## Common fault causes
- Sequential scan.
- Cold cache.
- Working set too large.
- Plan change.

## Automatic evaluation
- This chart ranks physical heap-block read counter deltas by stable relation OID.
- Changing bounded membership and counter resets become missing evidence; correlate with OS latency and cache state.

## Checklist
- Review SQL touching top tables.
- Compare with OS disk reads.
- Check indexes and table statistics.
