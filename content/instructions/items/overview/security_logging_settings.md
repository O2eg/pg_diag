# Security Logging Settings

This item lists security-relevant PostgreSQL logging settings that do not match the expected audit posture.

## What this item shows
- Missing connection or disconnection logging.
- Log prefix missing timestamp, user, database, application, or client address fields.
- Statement/error logging settings that reduce incident review value.

## Checklist
- Enable `log_connections` and `log_disconnections` when audit policy requires login tracing.
- Keep `log_line_prefix` rich enough to identify user, database, app, client, process, and timestamp.
- Review `log_statement`, `log_min_error_statement`, and `log_error_verbosity` against local audit policy.
