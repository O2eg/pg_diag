# Transaction ID Wraparound Pressure

This instruction belongs to report item `server_log.wraparound_pressure`. The item is backed by `server_log.wraparound_pressure` (trusted Python source) and consumes the csvlog window collected with `--log-depth-time-min`.

## What this item shows
- Warnings `database "X" must be vacuumed within N transactions` and the stop-stage errors where the database no longer accepts commands.
- These messages otherwise drown among ordinary warnings with an `ok` severity; here any row is a `high` finding with the database name and remaining transaction budget.

## What to watch
- `transactions_left` shrinking between the first and last time seen: pressure is building faster than autovacuum relieves it.
- The stop-stage message: the cluster is already refusing writes in that database.

## Common fault causes
- Long-running or abandoned transactions pinning xmin.
- Unused replication slots or prepared transactions holding the horizon.
- Autovacuum starved by cost limits or blocked by locks on huge tables.

## Automatic evaluation
- `high`: any wraparound warning or stop-stage error in the window.
- `ok`: none.
- An empty result with an incomplete window is reported as unproven, not as absence.

## Related report items
- [storage_vacuum.database_wraparound](#item-storage_vacuum.database_wraparound) — Live age() view of the same risk.
- [activity_locks.long_transactions](#item-activity_locks.long_transactions) — Who is pinning the horizon right now.

## Checklist
- Run aggressive VACUUM in the named databases immediately.
- Kill or commit the transactions and slots holding xmin.
- Re-check age(datfrozenxid) after the vacuum completes.
