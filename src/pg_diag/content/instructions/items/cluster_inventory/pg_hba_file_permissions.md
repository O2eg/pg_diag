# pg_hba File Permissions

This instruction belongs to report item `cluster_inventory.pg_hba_file_permissions`.

This item reports `pg_hba.conf` file modes broader than the expected local security posture.

## What this item shows
- `pg_hba.conf` path reported by PostgreSQL.
- Modes for the main HBA file, recursively included files, and `include_dir` directories.
- Risk level for unsafe writes or unexpected file access.

## What to watch
- Findings whose severity or evidence differs from the approved cluster security baseline.
- Broad access, weak authentication, sensitive-file exposure, or missing controls that compound other findings.

## Common fault causes
- Package or cloud defaults, legacy compatibility, incomplete hardening, or undocumented operational exceptions.
- A change in one security layer without corresponding role, HBA, filesystem, or extension controls.

## Automatic evaluation

- `high`: group or other users can write `pg_hba.conf`.
- `medium`: group execute or any other-user access is present.
- More restrictive file modes than 0600/0640 are accepted; include directories must not be writable by group/other.

## Related report items
- [os.postgres_config_file_permissions](#item-os.postgres_config_file_permissions) — Review permissions on all PostgreSQL configuration files.
- [cluster_inventory.pgdata_permissions](#item-cluster_inventory.pgdata_permissions) — Check protection of the containing data directory.
- [cluster_inventory.pg_hba_insecure_auth_methods](#item-cluster_inventory.pg_hba_insecure_auth_methods) — Review the sensitive rules protected by this file.

## Checklist
- Keep HBA files at `0600`/`0640` or a more restrictive mode.
- Protect every included file and include directory, not only the main file.
- Keep write access limited to PostgreSQL administrators.
- Re-check permissions after package upgrades or configuration management changes.
