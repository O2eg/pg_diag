# PostgreSQL Process Inventory

This instruction belongs to report item `backend_os.postgres_process_tree`. The item is backed by `os.postgres_process_tree` (local shell script).

## What this item shows
- A local `ps ax` snapshot filtered by the process name `postgres` or `postmaster`.
- PID, PPID, user, process state, elapsed time, CPU percent, memory percent, and command text.
- PID/PPID relationships between the postmaster process, client backends, background workers, WAL processes, autovacuum workers, and parallel workers.

## What to watch
- More than one PostgreSQL process tree on a host where only one cluster should be running.
- A main `postgres` process with an unexpected data directory, service account, or startup command.
- Large bursts of client backends, parallel workers, autovacuum workers, WAL senders, or WAL receivers.
- Processes with high `%CPU`, high `%MEM`, long `ELAPSED`, or suspicious `STAT` flags such as stopped or uninterruptible sleep.

## Common fault causes
- Multiple PostgreSQL clusters or versions running on the same host.
- Stale or duplicate postmaster process after a failed stop, restart, failover, or manual startup.
- Connection storm, runaway parallel query, long maintenance job, autovacuum pressure, backup, replication, or restore activity.
- Collector running on a host different from the database server; in that case the item may be skipped or show the wrong local process tree.

## Checklist
- Confirm the main PostgreSQL process belongs to the expected cluster, data directory, service account, and port.
- Match suspicious PIDs with `backend_os.backend_activity`, `backend_os.backend_proc_cpu`, and `backend_os.backend_proc_io`.
- Group parallel worker PIDs with their leader backend before deciding which query is responsible.
- Check whether WAL sender, WAL receiver, backup, autovacuum, or maintenance processes explain the workload spike.
- Re-run a fresh local snapshot before terminating processes, because `ps` is a point-in-time view.

## Automatic evaluation
- This item is informational because expected clusters, users, and process counts are deployment-specific.
- Filtering uses the `comm` field, so collector commands merely containing the word `postgres` are not included.
