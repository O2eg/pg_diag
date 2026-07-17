# Database Backends

This instruction belongs to report item `snapshot_charts_db.database_backends`. The item is backed by `database.backends` (snapshot metric).

## What this item shows
- Number of backends connected to each named database over time.
- Connection count trend during the capture window.

## What to watch
- Backend count approaching limits.
- Sudden connection surge.
- Backends increasing while throughput drops.

## Common fault causes
- Pool burst.
- Connection leak.
- Retry storm.
- Slow transactions holding backends.

## Automatic evaluation
- This is a point gauge per database; the connection database includes the pg_diag connection itself.
- Compare with `max_connections`, reserved slots, pool limits, and other databases before assigning severity.

## Related report items
- [activity_locks.connection_pressure](#item-activity_locks.connection_pressure) — Compare backend counts with configured capacity.
- [snapshot_charts_db.activity_sessions_by_state](#item-snapshot_charts_db.activity_sessions_by_state) — Separate backend states.
- [cluster_inventory.login_roles_without_connection_limit](#item-cluster_inventory.login_roles_without_connection_limit) — Review roles that can contribute unbounded connections.

## Checklist
- Compare with connection pressure.
- Check pooler and application deployment events.
- Avoid raising max_connections before fixing pooling.
