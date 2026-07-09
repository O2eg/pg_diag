# Cryptographic Extensions

This item reports missing cryptographic extension support in the connected database.

## What this item shows
- Availability of `pgcrypto` and `pgsodium`.
- Installed version in the connected database.
- Risk level when no cryptographic extension is available or installed.

## Checklist
- Install `pgcrypto` or `pgsodium` where database-side hashing or encryption is required.
- Prefer explicit per-database extension installation over assuming package availability.
- Remember that these extensions do not replace filesystem or volume encryption.
