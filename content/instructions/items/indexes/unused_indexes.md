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

## Checklist
- Check stats age and business cycle.
- Confirm no constraints or rare jobs need the index.
- Drop candidates gradually and monitor write/read impact.
