# Top Tables By Index Block Read Rate

This instruction belongs to report item `snapshot_charts_db.tables_top_index_block_read_rate`. The item is backed by `objects.tables_top_index_block_read_rate` (snapshot metric).

## What this item shows
- Tables whose indexes have highest block read rate.
- Current physical index-read pressure by table.

## What to watch
- Index reads concentrated on one table.
- Index block reads aligned with storage latency.
- High reads for low-result queries.

## Common fault causes
- Large/bloated indexes.
- Low-selectivity index access.
- Cold cache.
- Index-heavy workload.

## Checklist
- Inspect index_workload for top table.
- Review query predicates and index design.
- Compare with index health size findings.
