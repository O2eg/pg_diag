# pg_hba File Permissions

This item reports `pg_hba.conf` file modes broader than the expected local security posture.

## What this item shows
- `pg_hba.conf` path reported by PostgreSQL.
- Modes for the main HBA file, recursively included files, and `include_dir` directories.
- Risk level for unsafe writes or unexpected file access.

## Automatic evaluation
- `high`: group or other users can write `pg_hba.conf`.
- `medium`: group execute or any other-user access is present.
- More restrictive file modes than 0600/0640 are accepted; include directories must not be writable by group/other.

## Checklist
- Keep HBA files at `0600`/`0640` or a more restrictive mode.
- Protect every included file and include directory, not only the main file.
- Keep write access limited to PostgreSQL administrators.
- Re-check permissions after package upgrades or configuration management changes.
