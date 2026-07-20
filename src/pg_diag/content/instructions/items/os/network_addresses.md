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

## Automatic evaluation
- No severity is assigned because expected interfaces and addresses require an environment baseline.
- `unsupported` means the `ip` utility was unavailable. A failure of both `ip -br addr` and the compatible `ip addr show` fallback is an error rather than partial success.

## Related report items
- [overview.listen_addresses_exposure](#item-overview.listen_addresses_exposure) — Compare host addresses with PostgreSQL listeners.
- [os.firewall_postgres_exposure](#item-os.firewall_postgres_exposure) — Check firewall evidence for the same interfaces.
- [cluster_inventory.pg_hba_broad_network_ranges](#item-cluster_inventory.pg_hba_broad_network_ranges) — Review client networks admitted by PostgreSQL.

## Checklist
- Compare with PostgreSQL listen_addresses, pg_hba, and replication configuration.
- Confirm monitoring and application endpoints use the expected address.
- Check standby and backup connectivity when addresses changed.
