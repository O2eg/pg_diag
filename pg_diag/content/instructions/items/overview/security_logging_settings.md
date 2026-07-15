# Security Logging Settings

This instruction belongs to report item `overview.security_logging_settings`. The item is backed by `security.security_logging_settings` (SQL query).

## What this item shows
- Missing connection or disconnection logging.
- Log prefix missing timestamp, user, database, application, or client address fields.
- Statement/error logging settings that reduce incident review value.

## What to watch
- `risk_level=medium` means the setting differs from the bundled audit posture and requires policy review.
- `log_min_error_statement` is accepted when it logs `error` or any more verbose level.
- An empty table means these selected settings match the bundled posture; it is not proof that all required events reach durable storage.

## Common fault causes
- Package defaults were retained without an audit baseline.
- A logging change was made but reload/restart requirements were not completed.
- Auditing is delegated to `pgaudit`, a managed-service facility, or an external collector that this SQL query cannot inspect.

## Applicability
- The check is cluster-setting evidence, not an effective end-to-end audit test.
- `log_statement=none` can be intentional when equivalent statement auditing is provided elsewhere.
- Richer logging can expose sensitive SQL values and increase storage volume; apply the local retention and redaction policy.

## Checklist
- Enable `log_connections` and `log_disconnections` when audit policy requires login tracing.
- Keep `log_line_prefix` rich enough to identify user, database, app, client, process, and timestamp.
- Review `log_statement`, `log_min_error_statement`, and `log_error_verbosity` against local audit policy.
- Confirm rotation, retention, forwarding, access control, and redaction outside this item.
