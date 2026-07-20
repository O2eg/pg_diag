# sudoers PostgreSQL Escalation

This instruction belongs to report item `os.sudoers_postgres_escalation`.
It is backed by local Python source `security.sudoers_postgres_escalation`.

## What this item shows
- Sudoers files and lines that mention postgres with broad commands or `NOPASSWD`.
- A short rule excerpt without expanding secrets.

## What to watch
- `NOPASSWD`, `ALL`, shell commands, or broad escalation to/from the postgres account.

## Automatic evaluation
- A matched `NOPASSWD` rule is `high`; other broad heuristic matches are `medium`.
- If no sudoers file can be read, the item is `unsupported`. Partial readability is reported as incomplete coverage; aliases, includes, and effective sudo policy still require `visudo`/`sudo -l` validation.

## Common fault causes
- Emergency access left in place, overly broad command aliases, included files unreadable to the collector, or wrapper scripts that permit command injection.

## Related report items
- [os.postgres_os_group_members](#item-os.postgres_os_group_members) — Identify OS principals that may inherit escalation paths.
- [os.postgres_service_hardening](#item-os.postgres_service_hardening) — Compare sudo policy with service restrictions.
- [os.postgres_cron_timer_scripts](#item-os.postgres_cron_timer_scripts) — Review scheduled commands that may invoke privileged tools.

## Checklist
- Avoid broad passwordless escalation to postgres.
- Restrict maintenance commands to audited wrappers.
- Review both `/etc/sudoers` and `/etc/sudoers.d`.
