# Duplicate Indexes

This instruction belongs to report item `indexes.duplicate_indexes`. The item is backed by `indexes.duplicate_indexes` (SQL query).

## What this item shows
- Indexes with identical key/operator/collation/predicate/expression fingerprints.
- True duplicate index candidates.
- Approximate duplicate maintenance and storage overhead from `relpages`.

## What to watch
- Duplicate unique/constraint-related structures.
- Large duplicate indexes.
- Duplicates created by repeated migrations.

## Common fault causes
- Migration rerun.
- Manual CREATE INDEX duplicated existing index.
- Constraint/index naming confusion.

## Automatic evaluation
- `medium` is assigned only when access method, uniqueness/exclusion, key count, key/include attributes, opclasses, collations, options, predicate, and expressions match.
- Constraint and extension dependencies still decide which index, if any, can be removed.
- At most 3,000 largest valid indexes by `relpages` are fingerprinted. Duplicate groups outside that sample may be omitted.
- `sampled_index_count` and `estimated_total_index_size_bytes` describe only that sample; no exact size function is called.

## Related report items
- [indexes.redundant_indexes](#item-indexes.redundant_indexes) — Review broader prefix-overlap findings.
- [indexes.unused_indexes](#item-indexes.unused_indexes) — Check whether duplicate definitions serve active workloads.
- [object_workload.index_workload](#item-object_workload.index_workload) — Compare index usage before removal.

## Checklist
- Confirm dependencies before drop.
- Keep one valid index.
- Remove duplicates with production-safe DDL.
