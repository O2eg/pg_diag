# Schema Privilege Matrix

This item shows schema owner, grantee, `USAGE`, `CREATE`, and object counts for user schemas.

## What this item shows
- One row per schema/grantee.
- Schema-level `USAGE`, `CREATE`, and grant option flags.
- Table, sequence, view, and function counts in the schema.

## Checklist
- Remove unexpected PUBLIC `CREATE`.
- Verify schema owner roles match the deployment model.
- Use the matrix to spot schemas with unusually broad access.
