# Session Usage By Role

This instruction belongs to report item `users_roles.session_usage`. The item is backed by `roles.session_usage` (SQL query).

## What this item shows
- Current client sessions per role from `pg_stat_activity`: total, active, idle, and idle-in-transaction counts, the per-role `connection_limit`, and `limit_utilization_pct`.
- Distinct databases and client addresses, local socket sessions, application names, and the oldest session and longest transaction ages.
- `state_hidden_count` counts sessions whose state is hidden from the collector role.

## What to watch
- Roles close to their connection limit; new connections will fail with "too many connections for role".
- Roles with many idle-in-transaction sessions, which hold locks and block vacuum.
- Service roles connecting from unexpected addresses or applications.
- Sessions of roles that should no longer be in use.

## Common fault causes
- Connection pools sized above the per-role limit.
- Applications that keep transactions open while waiting for user input.
- Shared roles used by several applications, which hides who is connected.

## Automatic evaluation
- `medium`: sessions use at least 90 percent of the per-role connection limit, or a role with a zero limit still has sessions.
- `unknown`: session states of other roles are hidden; grant `pg_read_all_stats` to the collector role.
- `ok`: all other roles.
- The list covers 1,000 roles with sessions; `result_truncated` marks partial coverage.

## Related report items
- [activity_locks.connection_pressure](#item-activity_locks.connection_pressure) — Compare with server-wide connection pressure.
- [activity_locks.session_states](#item-activity_locks.session_states) — Review session states across all roles.
- [cluster_inventory.login_roles_without_connection_limit](#item-cluster_inventory.login_roles_without_connection_limit) — Identify roles without a per-role limit.

## Checklist
- Align pool sizes with per-role connection limits.
- Investigate long idle-in-transaction sessions before they block maintenance.
- Use one role per application to keep attribution possible.
