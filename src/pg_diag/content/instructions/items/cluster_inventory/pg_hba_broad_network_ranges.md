# pg_hba Broad Network Ranges

This instruction belongs to report item `cluster_inventory.pg_hba_broad_network_ranges`.

This item lists `pg_hba.conf` host rules with universal or overly broad address ranges.

## What this item shows
- Rules using `all`, `0.0.0.0/0`, or `::/0`.
- Very broad IPv4 or IPv6 CIDR ranges.
- Network scope and risk reason for each matching rule.

## What to watch
- Findings whose severity or evidence differs from the approved cluster security baseline.
- Broad access, weak authentication, sensitive-file exposure, or missing controls that compound other findings.

## Common fault causes
- Package or cloud defaults, legacy compatibility, incomplete hardening, or undocumented operational exceptions.
- A change in one security layer without corresponding role, HBA, filesystem, or extension controls.

## Automatic evaluation

- `high`: universal, IPv4 `/8` or broader, or IPv6 `/32` or broader ranges.
- `medium`: IPv4 `/16` or broader, or IPv6 `/64` or broader, excluding loopback.
- Hostnames, `samehost`, and `samenet` cannot be safely expanded without network context.

## Related report items
- [overview.listen_addresses_exposure](#item-overview.listen_addresses_exposure) — Compare admitted networks with listening interfaces.
- [os.firewall_postgres_exposure](#item-os.firewall_postgres_exposure) — Check whether host firewall rules narrow exposure.
- [cluster_inventory.pg_hba_generic_database_or_user](#item-cluster_inventory.pg_hba_generic_database_or_user) — Review rules broad in both network and identity scope.

## Checklist
- Replace broad ranges with the smallest required CIDR ranges.
- Keep administrative access separate from application access.
- Combine broad client ranges only with strong authentication and TLS enforcement.
