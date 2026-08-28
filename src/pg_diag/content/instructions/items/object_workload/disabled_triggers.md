# Disabled User Triggers

This instruction belongs to report item `object_workload.disabled_triggers`. The item is backed by `objects.disabled_triggers` (SQL query).

## What this item shows
- User triggers with `tgenabled = 'D'`: they exist but never fire, in any session or replication role.
- The full trigger definition so its intended effect is visible without opening the schema.
- Internal constraint triggers are excluded.

## What to watch
- Disabled triggers that maintain derived data, audit trails, or queue tables: the data silently diverges while the trigger is off.
- Triggers disabled during a bulk load or migration and never re-enabled.

## Common fault causes
- ALTER TABLE ... DISABLE TRIGGER issued for a data load and not reverted.
- Emergency incident mitigation that became permanent by accident.

## Automatic evaluation
- Every disabled trigger reports `medium` for review; disabling can be a deliberate, documented decision.
- The list covers the first 1000 disabled triggers and marks truncation.

## Related report items
- [object_workload.table_workload](#item-object_workload.table_workload) — Write activity on the tables whose triggers are disabled.

## Checklist
- Confirm each disabled trigger is intentional and documented.
- Before re-enabling, reconcile the data the trigger should have maintained while it was off.
