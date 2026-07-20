# PGDATA Permissions

This instruction belongs to report item `cluster_inventory.pgdata_permissions`.

This item reports PostgreSQL data directory permissions broader than expected.

## What this item shows
- `data_directory` path reported by PostgreSQL.
- Directory mode visible to the local collector.
- Risk level for group or world access.

## What to watch
- Findings whose severity or evidence differs from the approved cluster security baseline.
- Broad access, weak authentication, sensitive-file exposure, or missing controls that compound other findings.

## Common fault causes
- Package or cloud defaults, legacy compatibility, incomplete hardening, or undocumented operational exceptions.
- A change in one security layer without corresponding role, HBA, filesystem, or extension controls.

## Automatic evaluation

- `high`: PGDATA grants any access to other OS users.
- `medium`: unexpected group permissions are present; 0700 and 0750 are accepted.
- The check requires local visibility of the server's actual `data_directory`.

## Related report items
- [os.postgres_config_file_permissions](#item-os.postgres_config_file_permissions) — Inspect sensitive files inside PGDATA.
- [cluster_inventory.pg_hba_file_permissions](#item-cluster_inventory.pg_hba_file_permissions) — Review HBA-specific protection.
- [os.tablespace_directory_permissions](#item-os.tablespace_directory_permissions) — Compare protection of external tablespace paths.

## Checklist
- Keep PGDATA permissions at `0700` or tightly controlled `0750`.
- Limit access to the PostgreSQL OS account and trusted administrators.
- Re-check permissions after restore, rsync, or package operations.
