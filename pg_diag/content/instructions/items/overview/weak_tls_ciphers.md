# Weak TLS Ciphers

This instruction belongs to report item `overview.weak_tls_ciphers`. The item is backed by `security.weak_tls_ciphers` (SQL query).

## What this item shows
- Current `ssl_ciphers` value.
- Cipher classes that allow weak, anonymous, export, or medium-strength classes.
- Risk level for each class.

## What to watch
- Explicit weak/anonymous/export classes and `3DES` tokens are `high`; `MEDIUM` is `medium`.
- An empty result means no recognized positive weak token was found in the configured expression.
- It does not prove the fully expanded OpenSSL cipher set is strong.

## Common fault causes
- Distribution defaults retain compatibility aliases for old clients.
- A cipher expression uses broad aliases whose effective expansion changes with OpenSSL versions.
- TLS termination happens outside PostgreSQL, making the server setting non-applicable to client traffic.

## Applicability
- `ssl_ciphers` controls TLS 1.2 and older; TLS 1.3 cipher suites are not evaluated by this item.
- Negated tokens beginning with `!` or `-` are exclusions and are not findings.

## Checklist
- Remove weak cipher classes such as `LOW`, `EXP`, `NULL`, `MD5`, `RC4`, `DES`, and `3DES`.
- Prefer a policy that allows only modern strong ciphers.
- Test client compatibility after tightening TLS ciphers.
- Validate the effective cipher list with the server's OpenSSL build and a controlled TLS client scan.
