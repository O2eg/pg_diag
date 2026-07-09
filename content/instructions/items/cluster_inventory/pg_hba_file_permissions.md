# pg_hba File Permissions

This item reports `pg_hba.conf` file modes broader than the expected local security posture.

## What this item shows
- `pg_hba.conf` path reported by PostgreSQL.
- File mode and parent directory mode.
- Risk level when file permissions are broader than `0600` or `0640`.

## Checklist
- Set `pg_hba.conf` to `0600` or `0640`.
- Keep write access limited to PostgreSQL administrators.
- Re-check permissions after package upgrades or configuration management changes.
