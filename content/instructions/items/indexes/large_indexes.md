# Indexes Large Relative To Table

This instruction belongs to report item `indexes.large_indexes`. The item is backed by `indexes.large_indexes` (SQL query).

## What this item shows
- Indexes larger than half of their table heap with usage counters.
- Large index storage and maintenance-cost candidates.
- Index/table size imbalance.

## What to watch
- Large index with low scan count.
- Many large indexes on hot write table.
- Index size driven by wide columns or expressions.

## Common fault causes
- Bloat.
- Wide covering index.
- Low-selectivity multi-column index.
- Retention growth.

## Automatic evaluation
- This ratio is informational: a legitimate narrow table can have an index larger than its heap.
- Catalog page estimates select at most 100 candidates before exact size functions run.
- Usage counters are cumulative from the reported `stats_reset`; size ratio alone is not bloat evidence.

## Checklist
- Check usage before dropping or rebuilding.
- Consider REINDEX only when bloat is confirmed.
- Review index design against actual query predicates.
