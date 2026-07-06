# Top Tables By HOT Update Rate

This instruction belongs to report item `snapshot_charts_db.tables_top_hot_update_rate`. The item is backed by `objects.tables_top_hot_update_rate` (snapshot metric).

## What this item shows
- Tables with highest HOT update rate.
- Updates that can avoid index changes.
- Which tables benefit from HOT-friendly updates.

## What to watch
- HOT updates high on expected hot tables.
- HOT low elsewhere despite high update rate.
- HOT rate change after index addition.

## Common fault causes
- Update workload touches non-indexed columns.
- Fillfactor leaves room for HOT.
- Index changes alter HOT eligibility.

## Checklist
- Use with update-rate and table_workload items.
- Do not treat high HOT as bad by itself.
- Review low HOT ratio on write-heavy tables.
