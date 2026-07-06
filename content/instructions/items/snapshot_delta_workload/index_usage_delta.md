# Index Usage Delta

This instruction belongs to report item `snapshot_delta_workload.index_usage_delta`. The item is backed by `objects.index_usage_delta` (snapshot metric).

## What this item shows
- Per-index scan, tuple read, tuple fetch, and block I/O deltas during the capture window.
- Which indexes were actively used during the snapshot window.

## What to watch
- High reads per scan.
- High tuple reads with low tuple fetches.
- Indexes active only during one workload phase.

## Common fault causes
- Low-selectivity index.
- Bitmap scans.
- Inefficient predicate.
- Batch/report workload.

## Checklist
- Compare with index health findings.
- Review query plans using the index.
- Do not drop active indexes based on cumulative unused findings alone.
