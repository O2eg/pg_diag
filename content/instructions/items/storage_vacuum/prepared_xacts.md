# Prepared Transactions

This instruction belongs to report item `storage_vacuum.prepared_xacts`. The item is backed by `vacuum.prepared_xacts` (SQL query).

## What this item shows
- Current two-phase commit prepared transactions.
- gid, owner, database, prepared timestamp, and age.
- Transactions that can retain locks and xmin until committed or rolled back.

## What to watch
- Any prepared transaction older than normal XA workflow.
- Prepared xacts from inactive applications.
- Prepared xacts blocking vacuum or DDL.

## Common fault causes
- Transaction manager failure.
- Application crash after PREPARE TRANSACTION.
- Manual testing left prepared xact open.

## Checklist
- Confirm transaction owner and business outcome.
- Commit or rollback through the transaction manager when possible.
- Resolve stale prepared xacts before wraparound/bloat work.
