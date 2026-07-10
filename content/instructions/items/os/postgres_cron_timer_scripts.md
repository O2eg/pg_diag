# PostgreSQL Cron And Timer Scripts

This instruction belongs to `os.postgres_cron_timer_scripts`, backed by local Python source `security.postgres_cron_timer_scripts`.

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

## Checklist
- Keep scheduled maintenance files writable only by trusted administrators.
- Avoid writable scripts executed as postgres.
- Review package and custom maintenance jobs separately.
