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

## Checklist
- Check usage before dropping or rebuilding.
- Consider REINDEX only when bloat is confirmed.
- Review index design against actual query predicates.
