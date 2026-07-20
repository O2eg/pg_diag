# Top Tables By Index Block Read Rate

This instruction belongs to report item `snapshot_charts_db.tables_top_index_block_read_rate`. The item is backed by `objects.tables_top_index_block_read_rate` (snapshot metric).

## What this item shows
- Tables whose indexes have highest block read rate.
- Current physical index-read pressure by table.

## Units
- `blocks/s` means index-block read counter increments per wall-clock second, aggregated across a table's indexes. A block uses the server's configured `block_size`.

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

## Related report items
- [object_workload.index_workload](#item-object_workload.index_workload) — Inspect index usage for affected tables.
- [snapshot_delta_workload.index_usage_delta](#item-snapshot_delta_workload.index_usage_delta) — Measure current index activity.
- [indexes.large_indexes](#item-indexes.large_indexes) — Check whether large indexes drive read pressure.

## Checklist
- Inspect index_workload for top table.
- Review query predicates and index design.
- Compare with index health size findings.
