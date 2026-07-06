# Network Addresses And Hosts

This instruction belongs to report item `os.network_addresses`. The item is backed by `os.network_addresses` (local host script).

## What this item shows
- Local network addresses, interfaces, and host name mappings.
- Networking context for client, replication, backup, and monitoring connectivity.

## What to watch
- Unexpected IP address, hostname, DNS mapping, or interface state.
- Multiple addresses where PostgreSQL or replication should bind only one.
- Address mismatch after failover or host rebuild.

## Common fault causes
- DNS drift.
- Network interface renumbering.
- Wrong host aliases.
- Container or VPN namespace confusion.

## Checklist
- Compare with PostgreSQL listen_addresses, pg_hba, and replication configuration.
- Confirm monitoring and application endpoints use the expected address.
- Check standby and backup connectivity when addresses changed.
