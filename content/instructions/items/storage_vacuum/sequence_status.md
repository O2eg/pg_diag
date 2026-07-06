# Sequence Exhaustion

This instruction belongs to report item `storage_vacuum.sequence_status`. The item is backed by `storage.sequence_status` (SQL query).

## What this item shows
- Sequence capacity, current value, max value, usage percentage, and related table context.
- Sequences approaching exhaustion.
- Whether sequence type or maxvalue is safe for current consumption.

## What to watch
- High percent used.
- Small integer-backed sequences on high-write tables.
- Sequences with cache/cycle settings that do not match expectations.

## Common fault causes
- ID type too small.
- Rapid insert growth.
- Manual setval advanced sequence.
- Cycle enabled unexpectedly.

## Checklist
- Estimate time to exhaustion from insert rate.
- Plan bigint or sequence maxvalue change before outage.
- Check application assumptions about ID width.
