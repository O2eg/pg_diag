# PostgreSQL Cron And Timer Scripts

This instruction belongs to report item `os.postgres_cron_timer_scripts`.
It is backed by local Python source `security.postgres_cron_timer_scripts`.

## What this item shows
- Cron or systemd file path.
- Referenced script path when detected.
- Group/world writable cron files or scripts.

## What to watch
- A scheduler definition or referenced maintenance executable writable by an untrusted account.

## Automatic evaluation
- World-writable files/scripts are `high`; group-writable paths are `medium`.
- No readable cron/systemd evidence is `unsupported`. The scan is heuristic and does not cover every external scheduler, user crontab, container orchestrator, or dynamically constructed command.

## Common fault causes
- Maintenance script deployed with permissive mode, shared automation group, package/custom timer drift, or a command pointing to a writable wrapper.

## Related report items
- [os.sudoers_postgres_escalation](#item-os.sudoers_postgres_escalation) — Review privileges used by scheduled commands.
- [os.world_writable_paths_in_pg_tree](#item-os.world_writable_paths_in_pg_tree) — Check scripts located under writable paths.
- [os.backup_repository_permissions](#item-os.backup_repository_permissions) — Review repositories used by backup schedules.

## Checklist
- Keep scheduled maintenance files writable only by trusted administrators.
- Avoid writable scripts executed as postgres.
- Review package and custom maintenance jobs separately.
