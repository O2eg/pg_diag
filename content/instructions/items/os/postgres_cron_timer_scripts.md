# PostgreSQL Cron And Timer Scripts

This item checks PostgreSQL-related cron, timer, and maintenance script paths.

## What this item shows
- Cron or systemd file path.
- Referenced script path when detected.
- Group/world writable cron files or scripts.

## Checklist
- Keep scheduled maintenance files writable only by trusted administrators.
- Avoid writable scripts executed as postgres.
- Review package and custom maintenance jobs separately.
