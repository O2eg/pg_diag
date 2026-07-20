# Top Tables By HOT Update Rate

This instruction belongs to report item `snapshot_charts_db.tables_top_hot_update_rate`. The item is backed by `objects.tables_top_hot_update_rate` (snapshot metric).

## What this item shows
- Tables with highest HOT update rate.
- Updates that can avoid index changes.
- Which tables benefit from HOT-friendly updates.

## Units
- `rows/s` means HOT-updated-row counter increments per wall-clock second for each table. It is an event rate, not the percentage of updates that were HOT.

## What to watch
- HOT updates high on expected hot tables.
- HOT low elsewhere despite high update rate.
- HOT rate change after index addition.

## Bounded samples
- Each SQL sample is ordered and limited before rows enter collector memory.
- Each column ranks deltas only for keys present in both adjacent bounded samples.
- Different table series between columns are expected; unmatched keys are not zero or errors.
- Counter decreases and invalid values are omitted and reported separately.

## Common fault causes
- Update workload touches non-indexed columns.
- Fillfactor leaves room for HOT.
- Index changes alter HOT eligibility.

## Automatic evaluation
- This chart ranks HOT update deltas for stable relation OIDs; HOT activity is usually beneficial relative to non-HOT updates.
- Interpret the rate against total updates rather than treating high HOT activity as a fault.

## Related report items
- [snapshot_charts_db.tables_top_update_rate](#item-snapshot_charts_db.tables_top_update_rate) — Compare HOT updates with all updates.
- [object_workload.table_workload](#item-object_workload.table_workload) — Review cumulative HOT and update counters.
- [snapshot_delta_workload.table_maintenance_delta](#item-snapshot_delta_workload.table_maintenance_delta) — Check maintenance activity on hot tables.

## Checklist
- Use with update-rate and table_workload items.
- Do not treat high HOT as bad by itself.
- Review low HOT ratio on write-heavy tables.
