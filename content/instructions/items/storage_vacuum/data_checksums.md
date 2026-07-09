# Data Checksums

This item reports disabled data page checksums or checksum failures visible in PostgreSQL statistics.

## What this item shows
- Whether `data_checksums` is enabled.
- Any checksum failures reported by `pg_stat_database`.
- Last visible checksum failure timestamp when PostgreSQL exposes it.

## Checklist
- Enable data checksums when initializing new production clusters where corruption detection is required.
- Investigate any checksum failures immediately.
- Treat checksum enablement as a migration or reinitialization task for existing clusters.
