# Top Indexes By Tuple Read Rate

This instruction belongs to report item `snapshot_charts_db.indexes_top_tuple_read_rate`. The item is backed by `objects.indexes_top_tuple_read_rate` (snapshot metric).

## What this item shows
- Indexes with highest tuple read rate.
- How many index entries are scanned per second.

## What to watch
- High tuple reads from one index.
- Reads much higher than fetches.
- Index scanning many entries for few rows.

## Bounded samples
- Each SQL sample is ordered and limited before rows enter collector memory.
- Each column ranks deltas only for keys present in both adjacent bounded samples.
- Different index series between columns are expected; unmatched keys are not zero or errors.
- Counter decreases and invalid values are omitted and reported separately.

## Common fault causes
- Low selectivity.
- Range scans too broad.
- Missing better composite index.

## Checklist
- Compare with tuple fetch rate.
- Review predicates and column order.
- Check table/index bloat if reads are excessive.
