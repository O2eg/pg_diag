# Listen Addresses Exposure

This item reports `listen_addresses` values that expose PostgreSQL beyond loopback.

## What this item shows
- Current `listen_addresses` value.
- Individual non-loopback or wildcard listen addresses.
- Risk level for wildcard network exposure.

## Checklist
- Bind PostgreSQL only to required interfaces.
- Prefer explicit private addresses over `*`, `0.0.0.0`, or `::`.
- Review `pg_hba.conf` and firewall rules together with this setting.
