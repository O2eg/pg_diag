# Cached Relation Kinds

This instruction belongs to report item `buffer_cache.relation_kinds`.

## What this item shows
- Current-database cached blocks grouped by `pg_class.relkind`.
- Tables, indexes, TOAST, materialized views, and unresolved files.

## What to watch
- Large changes in the table, index, or TOAST composition.

## Common fault causes
- Workload shifts, bulk access, maintenance, or cache warming.

## Automatic evaluation
- No severity is assigned; cached occupancy is not read traffic.

## Related report items
- [buffer_cache.top_relations](#item-buffer_cache.top_relations) — Resolve relation-kind totals to individual relations.
- [buffer_cache.relation_coverage](#item-buffer_cache.relation_coverage) — Check normalized cache coverage.
- [object_workload.table_io](#item-object_workload.table_io) — Compare cache composition with cumulative relation I/O.

## Checklist
- Use relation-level charts for object attribution.
- Investigate persistent unresolved files if they materially affect the result.
