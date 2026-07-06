# pg_stat_statements Capability Check

This instruction belongs to report item `sql_workload.pg_stat_statements_capabilities`. The item is backed by `statements.pg_stat_statements_capabilities` (SQL query).

## What this item shows
- Whether pg_stat_statements is installed and usable.
- Preload, query_id, tracking, max entries, and related settings needed for statement diagnostics.
- Capability gaps that explain missing or incomplete Top SQL sections.

## What to watch
- Extension not installed in the target database.
- shared_preload_libraries missing pg_stat_statements.
- compute_query_id disabled.
- Tracking set too narrowly for the workload.

## Common fault causes
- Extension installed after server start without restart.
- Insufficient database privileges.
- Query tracking disabled by configuration.
- pg_stat_statements.max too small for churny workloads.

## Checklist
- Fix capability gaps before relying on Top SQL tables.
- Restart PostgreSQL when preload changes require it.
- Reset pg_stat_statements only when a clean measurement window is intended.
