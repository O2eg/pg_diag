# sudoers PostgreSQL Escalation

This item checks sudoers rules involving the postgres OS account.

## What this item shows
- Sudoers files and lines that mention postgres with broad commands or `NOPASSWD`.
- A short rule excerpt without expanding secrets.

## Checklist
- Avoid broad passwordless escalation to postgres.
- Restrict maintenance commands to audited wrappers.
- Review both `/etc/sudoers` and `/etc/sudoers.d`.
