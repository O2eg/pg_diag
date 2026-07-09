# Authentication Timeout And Delay

This instruction belongs to report item `overview.auth_timeout_delay`. The item is backed by `security.auth_timeout_delay` (SQL query).

## What this item shows
- `authentication_timeout` values that are disabled or too high.
- Missing failed-authentication delay configuration.
- Related `auth_delay` settings when available.

## What to watch
- Disabled `authentication_timeout` is `high`; a value above 60 seconds is `medium`.
- Missing recognized failed-authentication delay is `medium` under the bundled posture.
- An empty result means the selected settings match this posture, not that brute-force protection is effective end to end.

## Common fault causes
- PostgreSQL package defaults are used without a host/network rate limiter.
- `auth_delay` is installed but its exact preload name or delay setting is absent.
- A proxy, firewall, PAM stack, or identity provider implements throttling that PostgreSQL settings cannot show.

## Applicability
- Failed-auth delay is a policy choice and can consume server resources during abusive connection storms.
- Evaluate connection pooling, network rate limiting, lockout policy, and denial-of-service risk before enabling delay.

## Checklist
- Keep `authentication_timeout` enabled and reasonably short.
- Configure a failed-authentication delay with `auth_delay` or the server's available equivalent.
- Review these settings after PostgreSQL major upgrades.
- Confirm effective throttling with a controlled authentication test outside production traffic.
