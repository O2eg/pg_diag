# Log Replication Commands

This instruction belongs to report item `replication.log_replication_commands`. The item is backed by `security.log_replication_commands` (SQL query).

## What this item shows
- A finding row when cluster setting `log_replication_commands` is not `on`, including source and pending-restart state.
- Logging posture only; it does not prove that logs are retained, protected, shipped, or reviewed.

## What to watch
- Whether replication-command auditing is required by the deployment's security or compliance policy.
- Log destination, retention, access control, and volume alongside this setting.

## Automatic evaluation
- `medium`: replication commands are not logged and require a policy review.
- Empty/`ok` means the setting is enabled, not that the complete audit pipeline is healthy.

## Common fault causes
- Default configuration, log-volume concerns, or an external audit design that intentionally uses other controls.
- Setting changed in a configuration file but not reloaded.

## Related report items
- [overview.security_logging_settings](#item-overview.security_logging_settings) — Review the broader server logging posture.
- [os.log_file_permissions](#item-os.log_file_permissions) — Verify protection of replication audit logs.
- [replication.replication_roles](#item-replication.replication_roles) — Identify principals capable of replication commands.

## Checklist
- Confirm the audit requirement and estimate log volume before enabling.
- Validate effective configuration source and reload/restart requirements.
- Correlate with replication roles, HBA rules, log permissions, retention, and forwarding.
