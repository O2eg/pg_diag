# Sequence Table Owner Mismatch

This item lists owned sequences whose owner differs from the dependent table owner.

## What this item shows
- Sequence schema/name and owner.
- Dependent table and column.
- Table owner.

## Automatic evaluation
- Severity is `unknown`: different owners may be intentional and do not by themselves prevent sequence use.
- Results are bounded to 1000 dependencies; validate privileges and the migration ownership model.

## Checklist
- Align sequence and table ownership for application-owned tables.
- Review identity and serial columns after ownership changes.
- Re-run grants where sequence privileges are required by application roles.
