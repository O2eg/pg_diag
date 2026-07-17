# Core Dump Policy

This instruction belongs to report item `os.core_dump_policy`.
It is backed by local Python source `security.core_dump_policy`.

## What this item shows
- `fs.suid_dumpable`.
- `kernel.core_pattern`.

## What to watch
- Nonzero `fs.suid_dumpable` or a core pattern that may persist PostgreSQL process memory.

## Automatic evaluation
- Nonzero `suid_dumpable` is `high`; an enabled/nontrivial core pattern is `medium` for review.
- A pipe to systemd-coredump or another collector can be legitimate if storage, retention, and access are protected. Unreadable sysctls produce `unsupported`.

## Common fault causes
- Debugging enabled temporarily, distribution coredump defaults, service limits allowing dumps, or an unprotected crash collector.

## Related report items
- [os.postgres_env_secret_leaks](#item-os.postgres_env_secret_leaks) — Assess secrets that a core dump could expose.
- [os.postgres_service_hardening](#item-os.postgres_service_hardening) — Review service-level dump restrictions.
- [os.disk_encryption_status](#item-os.disk_encryption_status) — Check at-rest protection for dump storage.

## Checklist
- Disable unsafe core dumps for PostgreSQL.
- Route dumps to a protected collector if dumps are required.
- Treat dumps as sensitive because they may contain data and credentials.
