# WAL Receiver

This instruction belongs to report item `replication.wal_receiver`. The item is backed by `replication.wal_receiver` (SQL query).

## What this item shows
- WAL receiver status on a standby server.
- Upstream host, received LSN, latest message timestamps, and connection state.
- Whether this server is receiving WAL from an upstream primary.

## What to watch
- No receiver row on a standby where one is expected.
- Receiver connected to wrong upstream host.
- Stale latest message timestamp.

## Common fault causes
- Primary unreachable.
- Wrong primary_conninfo.
- Authentication or TLS failure.
- Network issue.

## Checklist
- Check this item only on standby servers.
- Compare upstream host with intended topology.
- Review PostgreSQL logs for connection failures.
