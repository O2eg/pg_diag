# Data Checksums

This instruction belongs to report item `storage_vacuum.data_checksums`. The item is backed by `security.data_checksums` (SQL query).

## What this item shows
- A finding when cluster page checksums are disabled or `pg_stat_database` reports checksum failures, including the latest visible failure timestamp.

## What to watch
- Any checksum failure, repeated failures, affected database/storage, and corroborating PostgreSQL/kernel logs.
- Disabled checksums relative to the deployment's corruption-detection policy.

## Automatic evaluation
- `high`: checksums are disabled or at least one checksum failure is reported.
- Empty/`ok` means enabled with no reported failure, not proof every page was recently read and verified.

## Common fault causes
- Storage/memory corruption, torn/offline modification, disabled cluster initialization, or a historical counter not yet investigated.

## Checklist
- Investigate failures immediately and preserve evidence/backups.
- Use the enablement procedure supported by the installed PostgreSQL version; do not improvise on production.
- Correlate with storage diagnostics and checksum verification tooling.
