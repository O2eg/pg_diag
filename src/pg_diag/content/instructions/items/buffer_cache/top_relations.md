# Top Relations In Buffer Cache

This instruction belongs to report item `buffer_cache.top_relations`.

## What this item shows
- The 30 largest current-database relation residents plus `Other`.
- Cache composition with independently selected members at each snapshot.

## Units
- `blocks` counts shared-buffer slots/pages attributed to each relation. One block uses the server's configured `block_size`; `kblocks` and `Mblocks` are SI-scaled block counts.

## What to watch
- Dominant relations and abrupt composition changes.

## Common fault causes
- Bulk access, index scans, maintenance, or workload changes.

## Automatic evaluation
- No severity is assigned. Missing members remain unknown, never zero.

## Related report items
- [buffer_cache.relation_coverage](#item-buffer_cache.relation_coverage) — Normalize residency against relation size.
- [buffer_cache.relation_residency_delta](#item-buffer_cache.relation_residency_delta) — Inspect cache gains and losses over time.
- [storage_vacuum.table_size_detailed](#item-storage_vacuum.table_size_detailed) — Compare cached blocks with relation size.

## Checklist
- Treat `Other` as the bounded remainder.
- Review explicitly labeled unresolved physical files before drawing conclusions.
