# Connection Pressure

This instruction belongs to report item `activity_locks.connection_pressure`. The item is backed by `activity.connection_pressure` (SQL query).

## What this item shows
- An instantaneous, cluster-wide count of `client backend` processes that consume `max_connections` slots.
- Ordinary, reserved-role, and total connection limits and remaining headroom. `reserved_connections` is reported as zero on PostgreSQL 10-15, where that setting does not exist.
- Active, idle, idle-in-transaction (including aborted), and actively waiting client-session counts.

## What to watch
- `ordinary_available_connections` at zero means ordinary roles can no longer connect.
- Low `reserved_role_available_connections` or `total_available_connections` means emergency access is being consumed.
- Many idle sessions often indicate oversized pools; many waiting sessions indicate occupied backends are also stalled.

## Automatic evaluation
- `high`: at most one total client connection slot remains.
- `medium`: ordinary-role headroom is at or below 5%, with a minimum threshold of two slots.
- The total count includes pg_diag's own connection because it consumes a real slot. State and wait breakdowns are complete only with sufficient statistics visibility, normally `pg_read_all_stats` or `pg_monitor`.

## Common fault causes
- Oversized connection pools or a connection leak.
- Slow transactions keeping backends occupied.
- Retry storms or too many independently sized application pools.

## Related report items
- [snapshot_charts_db.database_backends](#item-snapshot_charts_db.database_backends) — Inspect the connection-count trend by database.
- [snapshot_charts_db.activity_sessions_by_state](#item-snapshot_charts_db.activity_sessions_by_state) — Separate active, idle, and idle-in-transaction sessions.
- [backend_os.postgres_process_tree](#item-backend_os.postgres_process_tree) — Check whether a process burst accompanies connection pressure.

## Checklist
- Preserve superuser and reserved-role emergency access.
- Identify the applications and roles owning connection growth in `Session States`.
- Fix pool or leak behavior before raising `max_connections`, because a higher value increases server resource allocation.
- A collection error is not evidence of free capacity; this item normally returns exactly one row.
