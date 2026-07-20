# Relation Cache Coverage

This instruction belongs to report item `buffer_cache.relation_coverage`.

## What this item shows
- Cached percentage of each selected relation's current on-disk size.
- Coverage calculated with PostgreSQL `block_size` rather than a fixed block size.
- Only application relations are included. Relations in `pg_catalog`,
  `information_schema`, TOAST, temporary, and other `pg_*` schemas are excluded.

## What to watch
- Coverage loss for frequently accessed relations during cache churn.

## Common fault causes
- Competing working sets, bulk scans, relation growth, or truncation.

## Automatic evaluation
- No severity is assigned. Small relations can legitimately approach 100 percent.

## Related report items
- [buffer_cache.top_relations](#item-buffer_cache.top_relations) — Compare normalized coverage with absolute residency.
- [storage_vacuum.table_size_detailed](#item-storage_vacuum.table_size_detailed) — Review current relation sizes.
- [snapshot_delta_workload.table_io_delta](#item-snapshot_delta_workload.table_io_delta) — Check I/O for poorly covered relations.

## Checklist
- Compare similarly sized relations.
- Remember that relation growth changes the denominator.
