# Object Owner Drift

This item reports schemas where same-kind objects are owned by multiple roles.

## What this item shows
- Schema and object kind.
- Number of objects and distinct owners.
- Whether any object in the group is owned by a superuser.

## Automatic evaluation
- Severity is `unknown`: mixed owners are not intrinsically unsafe without an approved ownership baseline.
- Treat superuser-owned rows separately using the dedicated superuser ownership item.

## Checklist
- Pick an expected owner role per application schema.
- Normalize object ownership after migrations.
- Investigate superuser-owned objects first.
