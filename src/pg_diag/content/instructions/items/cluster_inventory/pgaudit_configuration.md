# pgAudit Configuration

This instruction belongs to report item `cluster_inventory.pgaudit_configuration`.

This item reports pgAudit preload and audit logging configuration gaps.

## What this item shows
- Whether `pgaudit` is present in `shared_preload_libraries`.
- Whether the extension is created in the connected database.
- Whether `pgaudit.log` is configured.

## What to watch
- Findings whose severity or evidence differs from the approved cluster security baseline.
- Broad access, weak authentication, sensitive-file exposure, or missing controls that compound other findings.

## Common fault causes
- Package or cloud defaults, legacy compatibility, incomplete hardening, or undocumented operational exceptions.
- A change in one security layer without corresponding role, HBA, filesystem, or extension controls.

## Automatic evaluation

- Severity is `unknown` when pgAudit is absent or has no log classes because audit requirements are deployment-specific.
- Preload detection tokenizes the comma-separated library list; extension creation is separate from preload state.

## Related report items
- [overview.security_logging_settings](#item-overview.security_logging_settings) — Review the base PostgreSQL logging posture.
- [os.log_file_permissions](#item-os.log_file_permissions) — Verify protection of audit output.
- [replication.log_replication_commands](#item-replication.log_replication_commands) — Check replication-specific audit coverage.

## Checklist
- Add `pgaudit` to `shared_preload_libraries` where audit logging is required.
- Configure `pgaudit.log` according to the audit policy.
- Create the `pgaudit` extension in databases that need object audit support.
