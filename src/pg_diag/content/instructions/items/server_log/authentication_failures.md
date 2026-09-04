# Authentication Failures

This instruction belongs to report item `server_log.authentication_failures`. The item is backed by `server_log.authentication_failures` (trusted Python source) and consumes the csvlog window collected with `--log-depth-time-min`.

## What this item shows
- Failed login attempts (SQLSTATE `28000`/`28P01`, `password authentication failed`, `no pg_hba.conf entry`) grouped by user, client address, and database, with counts and first and last time seen.
- The sanitized sample message for each group.
- Detection is based on SQLSTATE and remains available when `lc_messages` is not English; the displayed sample message stays in the server's language.

## What to watch
- Many failures for one user from one address: a broken service credential after rotation.
- Failures spread across many users or addresses: scanning or brute force against an exposed port.
- `no pg_hba.conf entry` groups: clients reaching the server from networks nobody planned for.

## Common fault causes
- Credential rotation not delivered to every consumer.
- Monitoring or batch jobs with expired passwords retrying forever.
- Database port exposed wider than pg_hba.conf intends.

## Automatic evaluation
- `medium`: any authentication failures exist in the window.
- `ok`: the collected window contains no authentication failures.

## Related report items
- [users_roles.hba_rules](#item-users_roles.hba_rules) — The authentication rules these attempts were evaluated against.
- [users_roles.password_validity](#item-users_roles.password_validity) — Expired credentials that cause repeating failures.

## Checklist
- Fix or disable credentials that fail repeatedly from known services.
- For unknown client addresses, verify network exposure and tighten pg_hba.conf.
- Consider fail2ban-style throttling where brute force is evident.
