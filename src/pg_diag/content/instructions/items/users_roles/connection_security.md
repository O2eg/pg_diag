# Connection Security By Role

This instruction belongs to report item `users_roles.connection_security`. The item is backed by `roles.connection_security` (SQL query).

## What this item shows
- Current client sessions per role split into TLS sessions, GSSAPI-encrypted sessions (PostgreSQL 12 and newer), local socket sessions, loopback TCP sessions, and unencrypted remote TCP sessions.
- Negotiated TLS versions and ciphers plus the smallest cipher key size per role.
- `encryption_unknown_session_count` counts sessions whose TLS state is hidden from the collector role.

## What to watch
- Any role with `remote_unencrypted_session_count` above zero; credentials and data cross the network in clear text.
- Old TLS versions such as `TLSv1` or `TLSv1.1` and weak ciphers.
- Administrative roles connecting over unencrypted TCP.

## Common fault causes
- `pg_hba.conf` rules using `host` instead of `hostssl` for network clients.
- Clients configured with `sslmode=prefer` or `disable`.
- Load balancers terminating TLS and forwarding plain TCP to PostgreSQL.

## Automatic evaluation
- `medium`: a role has non-loopback TCP sessions without TLS or GSSAPI encryption.
- `unknown`: TLS state of other roles is hidden; grant `pg_read_all_stats` to the collector role.
- `ok`: all other roles.
- The list covers 1,000 roles with sessions; `result_truncated` marks partial coverage.

## Related report items
- [overview.tls_server_configuration](#item-overview.tls_server_configuration) — Verify the server TLS configuration.
- [cluster_inventory.pg_hba_tls_enforcement](#item-cluster_inventory.pg_hba_tls_enforcement) — Find pg_hba.conf rules that allow unencrypted network connections.
- [users_roles.hba_rules](#item-users_roles.hba_rules) — Review the authentication rules the server currently applies.

## Checklist
- Replace `host` rules with `hostssl` for network clients.
- Require `sslmode=verify-full` in client configuration.
- Disable TLS versions and ciphers below the security policy.
