# Collation Version Mismatches

This instruction belongs to report item `indexes.collation_version_mismatches`. The item is backed by `indexes.collation_version_mismatches` (SQL query).

## What this item shows
- Collations whose version recorded at creation differs from what the operating system libc or ICU currently provides.
- On PostgreSQL 15 and newer the default collation of the connected database is checked as the `(database default)` row.
- `dependent_relation_count` counts relations that explicitly depend on the affected collation; objects using the database default are not counted individually.

## What to watch
- Any mismatch after an operating system upgrade, container base-image change, or ICU update.
- Indexes on text columns under a changed collation: their sort order may no longer match the index order, causing wrong query results and missed rows.
- Collation version tracking exists on PostgreSQL 13 and newer; older servers report this item as unsupported.

## Common fault causes
- glibc upgrades (notably 2.28) or ICU upgrades that changed sort order.
- Restoring a physical backup or attaching a standby on a host with a different library version.

## Automatic evaluation
- Every mismatched collation reports `high`; the check covers the first 1000 tracked collations.
- When more tracked collations exist than the check covered, a separate `[coverage]` row with `unknown` reports the incomplete coverage even if no mismatch was found.
- An empty result means every tracked collation matches the current library version.

## Related report items
- [indexes.invalid_indexes](#item-indexes.invalid_indexes) — Indexes already known to be unusable; collation mismatches can corrupt indexes silently instead.

## Checklist
- REINDEX every index that depends on a changed collation before trusting its query results.
- Refresh recorded versions with ALTER COLLATION ... REFRESH VERSION or ALTER DATABASE ... REFRESH COLLATION VERSION only after reindexing.
- Keep library versions identical across primaries and standbys.
