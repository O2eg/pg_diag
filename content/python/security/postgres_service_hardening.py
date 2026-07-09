from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    rows = _systemctl_service_hardening_findings(await _postgres_systemd_unit_names(ctx))
    if rows is None:
        rows = _systemd_file_hardening_findings()
    return _result(
        rows,
        ok_title="PostgreSQL systemd units include expected hardening directives",
        fail_title="PostgreSQL systemd unit hardening gaps found",
        recommendation="Use systemd hardening directives such as NoNewPrivileges, ProtectSystem, ProtectHome, PrivateTmp, and a tight CapabilityBoundingSet where compatible.",
        diagnostic_code="security_postgres_service_hardening",
    )
