# Top Tables By Index Block Read Rate

This instruction belongs to report item `snapshot_charts_db.tables_top_index_block_read_rate`. The item is backed by `objects.tables_top_index_block_read_rate` (snapshot metric).

## What this item shows
- Tables whose indexes have highest block read rate.
- Current physical index-read pressure by table.

## What to watch
- Index reads concentrated on one table.
- Index block reads aligned with storage latency.
- High reads for low-result queries.

## Bounded samples
- Each SQL sample is ordered and limited before rows enter collector memory.
- Each column ranks deltas only for keys present in both adjacent bounded samples.
- Different table series between columns are expected; unmatched keys are not zero or errors.
- Counter decreases and invalid values are omitted and reported separately.

## Common fault causes
- Large/bloated indexes.
- Low-selectivity index access.
- Cold cache.
- Index-heavy workload.

## Automatic evaluation
- This chart ranks physical index-block read counter deltas by stable relation OID.
- It aggregates all indexes of a table; use index-level and SQL evidence for attribution.

## Checklist
- Inspect index_workload for top table.
- Review query predicates and index design.
- Compare with index health size findings.
