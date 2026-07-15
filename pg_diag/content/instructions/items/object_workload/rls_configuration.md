# Row Level Security Configuration

This item reports RLS configurations that are inactive, incomplete, or not forced for table owners.

## What this item shows
- Tables with policies but disabled RLS.
- Tables with RLS enabled but no policies.
- Tables where RLS is not forced for table owners.

## Automatic evaluation
- `high`: policies exist while RLS itself is disabled.
- `unknown`: RLS is not forced for the table owner; compare that normal default with the application threat model.
- RLS enabled with no policies is `ok` because PostgreSQL applies default deny to affected non-bypass roles.

## Checklist
- Enable RLS when policies exist.
- Add explicit policies when access should be allowed; an empty policy set intentionally denies access.
- Use `FORCE ROW LEVEL SECURITY` where owners should also be constrained.
