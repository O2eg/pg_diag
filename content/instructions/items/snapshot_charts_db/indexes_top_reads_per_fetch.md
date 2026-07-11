# Top Indexes By Tuples Read Per Heap Fetch

This instruction belongs to report item `snapshot_charts_db.indexes_top_reads_per_fetch`. The item is backed by `objects.indexes_top_reads_per_fetch` (snapshot metric).

## What this item shows
- Index-entry delta (`idx_tup_read`) divided by per-index heap-fetch delta (`idx_tup_fetch`).
- A logical executor ratio, not block reads per row and not a direct bloat metric.

## What to watch
- Many index entries returned for few simple index-scan heap fetches.
- A sudden ratio change together with a plan change.

## Bounded samples
- Samples are bounded before memory and matched by stable index OID at adjacent endpoints.
- Zero heap-fetch delta, changing membership, and counter decreases yield missing evidence rather than infinity or zero.

## Common fault causes
- Bitmap scans, index-only scans, dead entries, broad predicates, or low selectivity.

## Automatic evaluation
- This chart is informational because several efficient plan types naturally raise the ratio.

## Checklist
- Inspect actual plans and tuple/block I/O evidence; do not infer REINDEX or index removal from this ratio.
