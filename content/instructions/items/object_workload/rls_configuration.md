# Row Level Security Configuration

This item reports RLS configurations that are inactive, incomplete, or not forced for table owners.

## What this item shows
- Tables with policies but disabled RLS.
- Tables with RLS enabled but no policies.
- Tables where RLS is not forced for table owners.

## Checklist
- Enable RLS when policies exist.
- Add explicit policies before enabling RLS on application tables.
- Use `FORCE ROW LEVEL SECURITY` where owners should also be constrained.
