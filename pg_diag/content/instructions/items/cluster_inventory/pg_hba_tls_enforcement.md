# pg_hba TLS Enforcement

This item lists non-loopback `pg_hba.conf` rules that can allow unencrypted TCP connections.

## What this item shows
- Non-loopback `host` or `hostnossl` rules that are not `reject`.
- Address scope and server `ssl` setting for context.

## Automatic evaluation
- `high`: a non-loopback `host` or `hostnossl` allow rule can match without TLS/GSS enforcement.
- Loopback/samehost and reject rules are excluded; `hostssl` and `hostgssenc` enforce their transports.
- First-match ordering and external TLS termination still require deployment context.

## Checklist
- Use `hostssl` or `hostgssenc` for remote client rules.
- Reject or remove plain `host` and `hostnossl` rules for non-loopback clients.
- Verify TLS protocol and cipher policy separately.
