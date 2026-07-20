# Never Used Indexes

This instruction belongs to report item `indexes.unused_indexes`. The item is backed by `indexes.unused_indexes` (SQL query).

## What this item shows
- Non-unique btree indexes with no scans in current statistics.
- Candidate indexes that may add write overhead without observed read benefit.
- Index size and relation context for unused candidates.

## What to watch
- Large unused indexes.
- Many unused indexes on hot write tables.
- Stats reset recently making usage evidence incomplete.

## Common fault causes
- Obsolete query pattern.
- Over-indexing from ORM migrations.
- Rare monthly/reporting workload not seen since reset.
- New index not yet used.

## Automatic evaluation
- `medium`: zero scans for at least 30 days, at least 100,000 table writes, and no matching foreign-key prefix.
- `unknown`: the observation window is shorter/unknown, write evidence is weak, or the index supports a foreign key.
- The result is a bounded candidate list; zero scans never authorize an automatic drop.

## Related report items
- [object_workload.index_workload](#item-object_workload.index_workload) — Review cumulative scans before considering removal.
- [snapshot_delta_workload.index_usage_delta](#item-snapshot_delta_workload.index_usage_delta) — Check activity during the capture window.
- [indexes.redundant_indexes](#item-indexes.redundant_indexes) — Determine whether another index covers the same access path.

## Checklist
- Check stats age and business cycle.
- Confirm no constraints or rare jobs need the index.
- Drop candidates gradually and monitor write/read impact.
