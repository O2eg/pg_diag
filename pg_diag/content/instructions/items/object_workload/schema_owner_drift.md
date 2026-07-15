# Schema Owner Drift

This item lists user objects whose owner differs from their containing schema owner.

## What this item shows
- Object kind, schema, object name, object owner, and schema owner.
- Objects from PostgreSQL system schemas are excluded.

## Automatic evaluation
- Severity is `unknown` until the result is compared with the intended owner-role matrix.
- Output is bounded to 1000 objects.

## Checklist
- Verify whether the schema owner should also own contained objects.
- Fix accidental drift from manual DDL or migrations run under the wrong role.
- Keep exceptions documented for shared schemas.
