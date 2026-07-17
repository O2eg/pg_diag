# pg_hba TLS Enforcement

This instruction belongs to report item `cluster_inventory.pg_hba_tls_enforcement`.

This item lists non-loopback `pg_hba.conf` rules that can allow unencrypted TCP connections.

## What this item shows
- Non-loopback `host` or `hostnossl` rules that are not `reject`.
- Address scope and server `ssl` setting for context.

## What to watch
- Findings whose severity or evidence differs from the approved cluster security baseline.
- Broad access, weak authentication, sensitive-file exposure, or missing controls that compound other findings.

## Common fault causes
- Package or cloud defaults, legacy compatibility, incomplete hardening, or undocumented operational exceptions.
- A change in one security layer without corresponding role, HBA, filesystem, or extension controls.

## Automatic evaluation

- `high`: a non-loopback `host` or `hostnossl` allow rule can match without TLS/GSS enforcement.
- Loopback/samehost and reject rules are excluded; `hostssl` and `hostgssenc` enforce their transports.
- First-match ordering and external TLS termination still require deployment context.

## Related report items
- [overview.tls_server_configuration](#item-overview.tls_server_configuration) — Verify server-side TLS settings.
- [os.tls_key_file_permissions](#item-os.tls_key_file_permissions) — Check private-key protection.
- [overview.weak_tls_ciphers](#item-overview.weak_tls_ciphers) — Review cipher strength.

## Checklist
- Use `hostssl` or `hostgssenc` for remote client rules.
- Reject or remove plain `host` and `hostnossl` rules for non-loopback clients.
- Verify TLS protocol and cipher policy separately.
