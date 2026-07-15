# TLS Server Configuration

This instruction belongs to report item `overview.tls_server_configuration`. The item is backed by `security.tls_server_configuration` (SQL query).

## What this item shows
- Whether server-side `ssl` is enabled.
- Minimum TLS protocol version.
- Missing certificate or private key settings when TLS is enabled.

## What to watch
- Disabled server TLS is `high` under the bundled network-security posture.
- TLS below 1.2 or an unenforced minimum is high/medium according to the returned row.
- An empty result validates selected settings only; it does not validate certificate files or active client sessions.

## Common fault causes
- TLS is terminated by a proxy or service mesh before traffic reaches PostgreSQL.
- The cluster serves only local Unix-domain sockets.
- Certificate/key paths use defaults, while file existence, permissions, expiry, or chain validity is broken.

## Applicability
- Severity depends on whether untrusted or shared networks can reach PostgreSQL directly.
- This SQL check cannot prove certificate validity, hostname matching, client verification, or effective HBA `hostssl` enforcement.

## Checklist
- Enable TLS where clients connect over untrusted networks.
- Require TLSv1.2 or newer.
- Keep certificate and key files managed by the PostgreSQL OS account.
- Inspect certificate/key files and sample active sessions in `pg_stat_ssl` before declaring TLS healthy.
