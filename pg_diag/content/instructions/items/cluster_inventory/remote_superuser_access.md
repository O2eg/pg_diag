# Remote Superuser Access

This instruction belongs to report item `cluster_inventory.remote_superuser_access`.

## What this item shows

This item checks whether `pg_hba.conf` contains `host*` rules that allow PostgreSQL superusers to connect through network authentication.

The check reads the `hba_file` setting from PostgreSQL, parses the local `pg_hba.conf` file, follows `include`, `include_if_exists`, and `include_dir` directives, expands `@` user files, and evaluates direct superuser names, `all`, and `+role` membership.

## What to watch
- Findings whose severity or evidence differs from the approved cluster security baseline.
- Broad access, weak authentication, sensitive-file exposure, or missing controls that compound other findings.

## Common fault causes
- Package or cloud defaults, legacy compatibility, incomplete hardening, or undocumented operational exceptions.
- A change in one security layer without corresponding role, HBA, filesystem, or extension controls.

## Automatic evaluation
- `high`: a matching login superuser uses trust, or a non-loopback rule is reachable according to `listen_addresses`.
- `medium`: a loopback/samehost host rule matches a login superuser.
- Includes and netmask notation are parsed, but rows are potential matches: PostgreSQL first-match ordering can shadow a later rule.

## Related report items
- [overview.listen_addresses_exposure](#item-overview.listen_addresses_exposure) — Confirm whether PostgreSQL listens on reachable interfaces.
- [os.firewall_postgres_exposure](#item-os.firewall_postgres_exposure) — Check host firewall evidence.
- [cluster_inventory.pg_hba_broad_network_ranges](#item-cluster_inventory.pg_hba_broad_network_ranges) — Review broad HBA source networks.
- [cluster_inventory.pg_hba_insecure_auth_methods](#item-cluster_inventory.pg_hba_insecure_auth_methods) — Check authentication strength on matching rules.

## Checklist

- Treat any `high` severity result as a security finding.
- Remove superusers from `host`, `hostssl`, `hostnossl`, `hostgssenc`, and `hostnogssenc` rules.
- Prefer local Unix socket access with `peer` authentication for superusers.
- Use non-superuser roles for remote administration and controlled privilege escalation.
- Reload PostgreSQL configuration after changing `pg_hba.conf`.
