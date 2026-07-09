# Sequence Table Owner Mismatch

This item lists owned sequences whose owner differs from the dependent table owner.

## What this item shows
- Sequence schema/name and owner.
- Dependent table and column.
- Table owner.

## Checklist
- Align sequence and table ownership for application-owned tables.
- Review identity and serial columns after ownership changes.
- Re-run grants where sequence privileges are required by application roles.
