# PostgreSQL Service Hardening

This instruction belongs to report item `os.postgres_service_hardening`.
It is backed by local Python source `security.postgres_service_hardening`.

## What this item shows
- PostgreSQL systemd unit name and effective properties from `systemctl show`.
- Missing directives such as `NoNewPrivileges`, `ProtectSystem`, `ProtectHome`, `PrivateTmp`, or `CapabilityBoundingSet`.

## What to watch
- Missing effective restrictions or broad capabilities retained by the active PostgreSQL unit.

## Automatic evaluation
- Each missing/broad directive is `medium`; compatibility with extensions, tablespaces, backup agents, and custom paths must be tested before remediation.
- If effective `systemctl show` evidence is unavailable, the result is `unsupported`; raw unit-file parsing is deliberately not treated as equivalent because it cannot reliably merge vendor units and drop-ins.

## Common fault causes
- Distribution unit defaults, custom overrides, package upgrades, or hardening disabled to accommodate filesystem/tooling access.

## Related report items
- [os.sudoers_postgres_escalation](#item-os.sudoers_postgres_escalation) — Review external privilege-escalation paths.
- [os.core_dump_policy](#item-os.core_dump_policy) — Check whether the service can expose memory through dumps.
- [os.postgres_env_secret_leaks](#item-os.postgres_env_secret_leaks) — Check secrets visible in the service environment.

## Checklist
- Apply compatible systemd hardening options.
- Test package upgrades and service reloads after overrides.
- Keep exceptions documented for extensions or tooling that need broader OS access.
