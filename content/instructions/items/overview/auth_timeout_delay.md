# Authentication Timeout And Delay

This item reports authentication timeout or failed-authentication delay settings that do not match the expected security posture.

## What this item shows
- `authentication_timeout` values that are disabled or too high.
- Missing failed-authentication delay configuration.
- Related `auth_delay` settings when available.

## Checklist
- Keep `authentication_timeout` enabled and reasonably short.
- Configure a failed-authentication delay with `auth_delay` or the server's available equivalent.
- Review these settings after PostgreSQL major upgrades.
