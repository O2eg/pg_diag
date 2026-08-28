# Configuration File Errors

This instruction belongs to report item `cluster_inventory.configuration_file_errors`. The item is backed by `cluster.configuration_file_errors` (SQL query).

## What this item shows
- Entries from `pg_file_settings` that the server cannot apply (`error` set) or that are overridden by a later entry for the same parameter or by ALTER SYSTEM.
- File name and line number for every reported entry, so the exact line can be fixed.
- An empty result means every configuration file entry is applied cleanly.

## What to watch
- Entries with an error: the intended value is silently not in effect, and some errors block the next server start.
- Overridden entries that disagree with the winning value; they confuse every future configuration review.
- Reading `pg_file_settings` requires membership in `pg_read_all_settings` (included in `pg_monitor`); an item error usually means the collector role lacks it.

## Common fault causes
- Typos or invalid values edited directly into postgresql.conf.
- The same parameter set both in postgresql.conf and via ALTER SYSTEM.
- Include files applied in an unexpected order.

## Automatic evaluation
- Entries with a parse or apply error report `high`.
- Overridden entries report `ok` with an explanatory reason; the list covers the first 1000 problem entries and marks truncation.

## Related report items
- [cluster_inventory.pending_restart_settings](#item-cluster_inventory.pending_restart_settings) — Applied changes still waiting for a restart.
- [overview.pg_settings](#item-overview.pg_settings) — The effective configuration the server is actually using.

## Checklist
- Fix every entry with an error before the next reload or restart.
- Remove duplicate entries so each parameter has exactly one authoritative source.
