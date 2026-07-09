# pgAudit Configuration

This item reports pgAudit preload and audit logging configuration gaps.

## What this item shows
- Whether `pgaudit` is present in `shared_preload_libraries`.
- Whether the extension is created in the connected database.
- Whether `pgaudit.log` is configured.

## Checklist
- Add `pgaudit` to `shared_preload_libraries` where audit logging is required.
- Configure `pgaudit.log` according to the audit policy.
- Create the `pgaudit` extension in databases that need object audit support.
