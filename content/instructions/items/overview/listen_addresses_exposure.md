# Listen Addresses Exposure

This instruction belongs to report item `overview.listen_addresses_exposure`. The item is backed by `security.listen_addresses_exposure` (SQL query).

## What this item shows
- Current `listen_addresses` value.
- Individual non-loopback or wildcard listen addresses.
- Risk level for wildcard network exposure.

## What to watch
- Wildcards (`*`, `0.0.0.0`, `::`) are `high`; another non-loopback address is `medium`.
- An empty result means PostgreSQL binds only recognized loopback/empty values.
- A finding is exposure evidence, not proof that an unauthenticated or unauthorized client can connect.

## Common fault causes
- A default container or managed-service template binds all interfaces.
- HA, replication, backup, or application traffic intentionally requires a non-loopback listener.
- Firewall or HBA restrictions are maintained separately from the listener configuration.

## Applicability
- Effective reachability also depends on `pg_hba.conf`, host firewalls, security groups, routing, proxies, and network namespaces.
- Hostnames resolving to loopback are conservatively reported because this query does not resolve DNS.

## Checklist
- Bind PostgreSQL only to required interfaces.
- Prefer explicit private addresses over `*`, `0.0.0.0`, or `::`.
- Review `pg_hba.conf` and firewall rules together with this setting.
- Validate required replication, HA, and monitoring clients before narrowing listeners.
