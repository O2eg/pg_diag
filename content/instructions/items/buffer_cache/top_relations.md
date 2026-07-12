# Top Relations In Buffer Cache

## What this item shows
- The 30 largest current-database relation residents plus `Other`.
- Cache composition with independently selected members at each snapshot.

## What to watch
- Dominant relations and abrupt composition changes.

## Common fault causes
- Bulk access, index scans, maintenance, or workload changes.

## Automatic evaluation
- No severity is assigned. Missing members remain unknown, never zero.

## Checklist
- Treat `Other` as the bounded remainder.
- Review explicitly labeled unresolved physical files before drawing conclusions.
