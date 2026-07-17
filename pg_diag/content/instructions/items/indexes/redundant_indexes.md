# Redundant Indexes

This instruction belongs to report item `indexes.redundant_indexes`. The item is backed by `indexes.redundant_indexes` (SQL query).

## What this item shows
- Indexes covered by another index on the same relation.
- Candidate redundant structures that may duplicate maintenance cost.
- Column/predicate/operator coverage context.

## What to watch
- Large redundant index.
- Redundant index on write-heavy table.
- Subtle uniqueness or predicate difference.

## Common fault causes
- Repeated migration added overlapping index.
- Manual tuning not cleaned up.
- ORM generated similar index.

## Automatic evaluation
- Severity is `unknown`: the check reports only conservative btree left-prefix candidates with matching opclass, collation, sort options, predicate, and expressions.
- Constraint-backed candidate indexes are excluded, but INCLUDE coverage, workload, and other dependencies still require manual review.

## Related report items
- [indexes.duplicate_indexes](#item-indexes.duplicate_indexes) — Distinguish prefix redundancy from exact duplication.
- [indexes.unused_indexes](#item-indexes.unused_indexes) — Check whether either index is actually used.
- [object_workload.index_workload](#item-object_workload.index_workload) — Compare scan and tuple counters.

## Checklist
- Verify uniqueness, predicate, collation, opclass, and included columns.
- Keep the more useful or constraint-backed index.
- Use controlled DDL for drops.
