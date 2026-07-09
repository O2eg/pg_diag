# Firewall PostgreSQL Exposure

This item checks local firewall evidence when PostgreSQL listens beyond loopback.

## What this item shows
- PostgreSQL port and listen addresses.
- Local firewall lines mentioning the port when visible.
- Cases where firewall rules could not be inspected.

## Checklist
- Bind PostgreSQL only to trusted interfaces when possible.
- Restrict the PostgreSQL port to trusted source networks.
- Validate cloud, host, and network firewall layers together.
