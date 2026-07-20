# Firewall PostgreSQL Exposure

This instruction belongs to report item `os.firewall_postgres_exposure`.
It is backed by local Python source `security.firewall_postgres_exposure`.

## What this item shows
- PostgreSQL port and listen addresses.
- Local firewall lines mentioning the port when visible.
- Cases where firewall rules could not be inspected.

## What to watch
- A broad allow rule, no visible rule for the PostgreSQL port, or inability to inspect any supported firewall frontend.

## Automatic evaluation
- An obvious broad allow is `high`; missing local evidence is `medium`.
- Even with no obvious match, severity remains `unknown`: text matching cannot prove rule ordering, default policy, namespaces, cloud controls, or upstream firewalls. Loopback-only listening is the only direct pass case.

## Common fault causes
- Firewall managed outside the host, root-only ruleset access, NAT/container namespaces, rule aliases, or PostgreSQL bound broadly for replication/application access.

## Related report items
- [overview.listen_addresses_exposure](#item-overview.listen_addresses_exposure) — Compare firewall evidence with PostgreSQL listeners.
- [cluster_inventory.pg_hba_broad_network_ranges](#item-cluster_inventory.pg_hba_broad_network_ranges) — Review database-level network admission.
- [cluster_inventory.remote_superuser_access](#item-cluster_inventory.remote_superuser_access) — Check whether exposed paths can reach superusers.

## Checklist
- Bind PostgreSQL only to trusted interfaces when possible.
- Restrict the PostgreSQL port to trusted source networks.
- Validate cloud, host, and network firewall layers together.
