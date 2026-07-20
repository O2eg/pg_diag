# PostgreSQL Control Data

This instruction belongs to report item `overview.pg_controldata`. The item is backed by `cluster.pg_controldata` (Python source using SQL and database-host command access).

## What this item shows
- The exact `pg_controldata` binary selected from the `BINDIR` reported by database-host `pg_config`.
- The data directory reported by the connected server.
- Cluster system identifier, control/catalog versions, cluster state, checkpoint and WAL control fields.
- Storage-format constants initialized by `initdb`, including block and WAL segment sizes and checksum version.

## What to watch
- A server or catalog version inconsistent with the expected PostgreSQL installation.
- Cluster state other than normal production or archive recovery states expected for the host role.
- Data checksum version zero where checksums are required.
- Block, WAL segment, alignment, date-storage, or float representation values that differ between hosts expected to be physically compatible.
- A control-data binary or data directory path that belongs to an unexpected installation.

## Common fault causes
- Multiple PostgreSQL major versions installed on the same host.
- Service configuration points to an unintended data directory.
- Collector or SSH user cannot read the PostgreSQL data directory.
- `pg_config` in the database-host `PATH` belongs to another PostgreSQL major version.
- The matching PostgreSQL server package is incomplete and lacks `pg_controldata`.

## Automatic evaluation
- This item is informational and does not infer severity from individual control fields.
- Failure to resolve a matching binary, execute `pg_controldata`, or read the data directory is reported as an item error with the original reason.
- The item never modifies the data directory and runs only once per report.

## Related report items
- [storage_vacuum.data_checksums](#item-storage_vacuum.data_checksums) — Cross-check the data-checksum state.
- [wal_io_checkpoints.wal_position](#item-wal_io_checkpoints.wal_position) — Relate control-file WAL state to the live cluster position.

## Checklist
- Compare the system identifier and format constants across primary and standby hosts.
- Confirm that `DATA_DIRECTORY` and `PG_CONTROLDATA` refer to the intended PostgreSQL instance.
- Compare checksum version with the dedicated Data Checksums item.
- Use the same PostgreSQL major-version utility as the running server when validating output manually.
