# Log Replication Commands

This item reports when replication commands are not logged.

## What this item shows
- Current `log_replication_commands` value.
- Configuration source and pending restart flag.
- Risk reason when replication commands are not audited.

## Checklist
- Enable `log_replication_commands` where replication activity must be auditable.
- Review log volume impact before enabling on busy systems.
- Correlate this with replication roles and replication `pg_hba.conf` rules.
