# Prepared Transactions

This instruction belongs to report item `storage_vacuum.prepared_xacts`. The item is backed by `vacuum.prepared_xacts` (SQL query).

## What this item shows
- Cluster-wide prepared two-phase transactions with database, GID, owner, timestamp, elapsed seconds, transaction ID, and XID age.

## What to watch
- Entries older than the owning transaction manager's normal completion window or retaining locks/xmin.

## Automatic evaluation
- No automatic severity: valid XA workflows can retain prepared transactions for deployment-specific periods.

## Common fault causes
- Coordinator/application failure, lost commit decision, network partition, or manual testing.

## Checklist
- Recover the authoritative commit/rollback decision from the coordinator.
- Do not guess the outcome or resolve another database's GID without owner confirmation.
- Empty means no prepared transactions exist cluster-wide.
