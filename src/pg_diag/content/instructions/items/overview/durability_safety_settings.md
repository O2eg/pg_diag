# Durability Safety Settings

This instruction belongs to report item `overview.durability_safety_settings`. The item is backed by `cluster.durability_safety_settings` (SQL query).

## What this item shows
- The cluster-wide values of `fsync`, `full_page_writes`, and `synchronous_commit` with their source and pending-restart flag, always listed so a safe configuration is visible, not silent.
- Permanent `ALTER ROLE SET` and `ALTER DATABASE SET` overrides of these settings from `pg_db_role_setting`, with their scope; the collector session cannot see them through `pg_settings`, so they are read from the catalog directly.
- `fsync` and `full_page_writes` protect against corruption; `synchronous_commit` only bounds how many confirmed transactions a crash can lose.

## What to watch
- `fsync=off` anywhere outside a disposable benchmark environment.
- `full_page_writes=off` without a storage stack that provably guarantees atomic 8kB writes.
- Permanent `synchronous_commit=off` overrides scoped to production roles or databases.
- Only `off` relaxes local crash durability: `local`, `remote_write`, and `remote_apply` still flush WAL locally on commit and differ only in standby guarantees.

## Common fault causes
- Benchmark or migration tuning left enabled in production.
- Configuration copied from an appliance or container image with unsafe defaults.
- A per-role override added for a bulk load and never removed.

## Automatic evaluation
- `fsync=off` and `full_page_writes=off` report `high`, whether cluster-wide or as a permanent override.
- `synchronous_commit=off` reports `medium` as an explicit confirmed-transaction loss window, not corruption; other modes report `ok` because their standby guarantees are assessed in the replication section.
- Ephemeral per-session `SET` commands are invisible to any catalog check and are out of scope here.

## Related report items
- [replication.synchronous_replication_status](#item-replication.synchronous_replication_status) — Whether synchronous standbys actually back the commit guarantees.
- [users_roles.role_database_settings](#item-users_roles.role_database_settings) — All per-role and per-database setting overrides.
- [overview.pg_settings](#item-overview.pg_settings) — The complete server configuration.

## Checklist
- Re-enable `fsync` and `full_page_writes` unless the platform documentation proves they are safe to disable.
- Confirm a relaxed `synchronous_commit` is a documented, accepted policy for the affected workload.
