# sudoers PostgreSQL Escalation

This instruction belongs to `os.sudoers_postgres_escalation`, backed by local Python source `security.sudoers_postgres_escalation`.

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

## Checklist
- Avoid broad passwordless escalation to postgres.
- Restrict maintenance commands to audited wrappers.
- Review both `/etc/sudoers` and `/etc/sudoers.d`.
