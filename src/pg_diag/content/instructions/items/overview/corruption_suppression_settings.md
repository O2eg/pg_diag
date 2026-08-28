# Corruption Suppression Settings

This instruction belongs to report item `overview.corruption_suppression_settings`. The item is backed by `cluster.corruption_suppression_settings` (SQL query).

## What this item shows
- The current values of `ignore_checksum_failure`, `zero_damaged_pages`, and `ignore_invalid_pages` with their source and pending-restart flag.
- Permanent `ALTER ROLE SET` and `ALTER DATABASE SET` overrides of these settings from `pg_db_role_setting`, with their scope; the collector session cannot see them through `pg_settings`, so they are read from the catalog directly.
- Each of these settings makes PostgreSQL continue past evidence of data corruption instead of failing.
- `ignore_invalid_pages` exists on PostgreSQL 13 and newer, so older servers list only two cluster rows.

## What to watch
- Any of these settings enabled outside a supervised data-rescue session.
- Permanent overrides scoped to an application role: every new session of that role silently suppresses corruption evidence while the cluster default looks safe.
- Values coming from the configuration file rather than a session: they survive restarts and keep masking corruption.
- Ephemeral per-session `SET` commands are invisible to any catalog check and are out of scope here.

## Common fault causes
- A one-off recovery session whose settings were persisted to postgresql.conf.
- Attempts to silence checksum errors instead of restoring from backup.

## Automatic evaluation
- Any enabled setting reports `high` with an explanation of the error class it hides.
- All settings off reports `ok` rows, so the safe state is confirmed explicitly.

## Related report items
- [storage_vacuum.data_checksums](#item-storage_vacuum.data_checksums) — Whether checksums are enabled and whether failures were reported.
- [overview.durability_safety_settings](#item-overview.durability_safety_settings) — Crash-safety settings that prevent corruption instead of hiding it.

## Checklist
- Disable these settings immediately after any rescue session ends.
- Treat checksum failures as a restore-from-backup signal, not as noise to suppress.
