# PostgreSQL Service Hardening

This item checks PostgreSQL systemd units for hardening directives.

## What this item shows
- PostgreSQL systemd unit name when effective `systemctl show` data is available, or unit file path as a fallback.
- Missing directives such as `NoNewPrivileges`, `ProtectSystem`, `ProtectHome`, `PrivateTmp`, or `CapabilityBoundingSet`.

## Checklist
- Apply compatible systemd hardening options.
- Test package upgrades and service reloads after overrides.
- Keep exceptions documented for extensions or tooling that need broader OS access.
