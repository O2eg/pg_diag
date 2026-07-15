# pg_hba Insecure Auth Methods

This item lists `pg_hba.conf` rules that use insecure authentication methods.

## What this item shows
- `trust`, `password`, `ident`, and `md5` authentication rules.
- File path, line number, connection type, database, user, address, and raw rule text.

## Automatic evaluation
- `high`: `trust` permits authentication without a password.
- `medium`: `password`, `ident`, or `md5` requires review; an `md5` rule can negotiate SCRAM when the stored verifier is SCRAM.
- Rule order and transport encryption must be considered before remediation.

## Checklist
- Replace `trust` with `peer` for local administration or strong authentication for network access.
- Prefer `scram-sha-256` over `md5`.
- Avoid `password` and `ident` for host rules.
