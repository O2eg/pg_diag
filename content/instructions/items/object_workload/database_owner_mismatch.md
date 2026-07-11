# Database Owner Mismatch

This item lists user objects whose owner differs from the connected database owner.

## What this item shows
- User schemas, relations, sequences, views, and functions.
- Current object owner and database owner.
- Extension-owned objects are excluded.

## Automatic evaluation
- Severity is `unknown`: dedicated database, schema, migration, and application owner roles commonly differ by design.
- Output is bounded to 1000 objects; absence from a truncated result is not proof of ownership alignment.

## Checklist
- Treat this as an ownership hygiene review, not an automatic failure.
- Document expected app, migration, and owner roles.
- Move unexpected ownership to the approved role set.
