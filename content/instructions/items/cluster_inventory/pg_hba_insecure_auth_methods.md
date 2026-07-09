# pg_hba Insecure Auth Methods

This item lists `pg_hba.conf` rules that use insecure authentication methods.

## What this item shows
- `trust`, `password`, `ident`, and `md5` authentication rules.
- File path, line number, connection type, database, user, address, and raw rule text.

## Checklist
- Replace `trust` with `peer` for local administration or strong authentication for network access.
- Prefer `scram-sha-256` over `md5`.
- Avoid `password` and `ident` for host rules.
