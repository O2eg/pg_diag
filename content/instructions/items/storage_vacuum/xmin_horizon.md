# Xmin Horizon Summary

This instruction belongs to report item `storage_vacuum.xmin_horizon`. The item is backed by `vacuum.xmin_horizon` (SQL query).

## What this item shows
- Oldest xmin horizons split by activity, replication, standby feedback, slots, and prepared transactions.
- Which subsystem is preventing vacuum from removing old row versions.
- Catalog and data horizon age context.

## What to watch
- Old activity xmin.
- Replication slot xmin or catalog_xmin.
- Prepared transaction holding old xmin.
- Standby feedback retaining dead rows.

## Common fault causes
- Long transaction.
- Lagging logical replication slot.
- Long standby query with hot_standby_feedback.
- Unresolved prepared xact.

## Checklist
- Identify the oldest horizon source.
- Clear blockers before vacuum/bloat remediation.
- Coordinate with replication owners before changing slots or feedback.
