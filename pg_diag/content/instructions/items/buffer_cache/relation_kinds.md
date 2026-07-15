# Cached Relation Kinds

## What this item shows
- Current-database cached blocks grouped by `pg_class.relkind`.
- Tables, indexes, TOAST, materialized views, and unresolved files.

## What to watch
- Large changes in the table, index, or TOAST composition.

## Common fault causes
- Workload shifts, bulk access, maintenance, or cache warming.

## Automatic evaluation
- No severity is assigned; cached occupancy is not read traffic.

## Checklist
- Use relation-level charts for object attribution.
- Investigate persistent unresolved files if they materially affect the result.
