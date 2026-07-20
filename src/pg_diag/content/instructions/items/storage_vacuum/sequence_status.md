# Sequence Exhaustion

This instruction belongs to report item `storage_vacuum.sequence_status`. The item is backed by `storage.sequence_status` (SQL query).

## What this item shows
- Up to 200 sequences with OID, data type, direction, min/max/start/current value, cache, cycle, capacity, and bounded table dependencies.
- Consumption is calculated from min toward max for ascending sequences and max toward min for descending sequences.
- Hidden/unavailable last values remain null; cycling sequences have no exhaustion percentage.

## What to watch
- Non-cycling sequences above 90/99 percent, narrow integer types, large cache/gaps, and application ID-width constraints.
- `CYCLE` avoids exhaustion by reusing values and can instead violate uniqueness assumptions.

## Automatic evaluation
- `high`: non-cycling visible sequence consumed at least 99% of its directional range.
- `medium`: at least 90%.
- Cycling or hidden-current-value rows remain `ok` without a fabricated percentage.

## Common fault causes
- Narrow type/range, rapid allocation, manual `setval`, cache loss/gaps, or an unexpected start/min/max configuration.

## Related report items
- [object_workload.sequence_privileges](#item-object_workload.sequence_privileges) — Verify access to sequences approaching exhaustion.
- [snapshot_delta_workload.table_dml_delta](#item-snapshot_delta_workload.table_dml_delta) — Check write activity associated with sequence consumption.
- [storage_vacuum.table_size_detailed](#item-storage_vacuum.table_size_detailed) — Review growth of the owning application tables.

## Checklist
- Estimate allocation rate from separate workload evidence.
- Validate column/application type before altering range or sequence type.
- The Top-200 bound can omit lower-ranked or hidden-value sequences.
