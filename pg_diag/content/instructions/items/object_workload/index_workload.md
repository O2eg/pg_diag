# Index Workload Counters

This instruction belongs to report item `object_workload.index_workload`. The item is backed by `objects.index_workload` (SQL query).

## What this item shows
- Cumulative index scans, tuple reads/fetches, and index cache I/O.
- Which indexes are actively used and how much work they perform.
- Index-level read amplification context.

## What to watch
- High idx_tup_read with low idx_tup_fetch.
- High index block reads.
- Indexes with scan count inconsistent with expectations.

## Common fault causes
- Low-selectivity index.
- Bitmap scan workload.
- Bloated or oversized index.
- Plan change.

## Automatic evaluation
- This item is informational; scan counts cannot prove that an index is useful or safe to remove.
- Counters are cumulative from `stats_reset`, and the bounded result contains the top 100 indexes by scan count.
- Exact index size is calculated only after the candidate limit.

## Checklist
- Use with index health findings.
- Review plans for indexes with high reads per useful fetch.
- Do not drop indexes that are active in current workload.
