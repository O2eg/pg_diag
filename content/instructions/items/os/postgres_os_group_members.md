# PostgreSQL OS Group Members

This instruction belongs to `os.postgres_os_group_members`, backed by local Python source `security.postgres_os_group_members`.

## What this item shows
- Additional users in the `postgres` group, including both supplemental members and accounts whose primary GID is the postgres group.

## What to watch
- Human, automation, or stale accounts that receive filesystem access through the service group.

## Automatic evaluation
- Every additional account is `medium` for policy review, not automatically `high`; authorized administrators may be intentional.
- If the host has no group named `postgres`, the check is `skipped/unknown` because alternative service-account layouts are outside its scope.

## Common fault causes
- Temporary maintenance access never removed, package/service account changes, or primary-group membership overlooked by `/etc/group` text inspection.

## Checklist
- Keep the postgres group limited to the service account and controlled administrators.
- Remove stale user memberships.
- Prefer audited sudo rules for maintenance access.
