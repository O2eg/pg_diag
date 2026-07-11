# Xmin Horizon Summary

This instruction belongs to report item `storage_vacuum.xmin_horizon`. The item is backed by `vacuum.xmin_horizon` (SQL query).

## What this item shows
- Cluster-wide oldest data/catalog xmin ages from activity, slots, WAL senders, and prepared transactions, observed from the connected database.
- Activity includes non-client backends with `backend_xmin`; WAL senders are counted in their dedicated component.

## What to watch
- One component dominating the data/catalog horizon and increasing between captures.
- Catalog xmin from logical slots, which can block catalog cleanup independently of data xmin.

## Automatic evaluation
- No automatic severity: acceptable transaction age depends on workload, churn, storage, and recovery objectives.

## Common fault causes
- Long/idle transactions, autovacuum or other backend snapshots, lagging slots/standbys, and unresolved prepared transactions.

## Checklist
- Open Xmin Horizon Blockers for the concrete PID/slot/GID.
- Compare captures; zero means no visible holder in that component.
- Coordinate with owners before terminating sessions or changing replication.
