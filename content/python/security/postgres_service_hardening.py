from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    unit_names = await _postgres_systemd_unit_names(ctx)
    rows = await run_blocking(_systemctl_service_hardening_findings, unit_names)
    if rows is None:
        return _unavailable_result(
            "Effective PostgreSQL systemd unit properties could not be read; raw unit files are not sufficient to evaluate merged drop-ins",
            "security_postgres_systemd_unavailable",
        )
    return _result(
        rows,
        ok_title="PostgreSQL systemd units include expected hardening directives",
        fail_title="PostgreSQL systemd unit hardening gaps found",
        recommendation="Use systemd hardening directives such as NoNewPrivileges, ProtectSystem, ProtectHome, PrivateTmp, and a tight CapabilityBoundingSet where compatible.",
        diagnostic_code="security_postgres_service_hardening",
    )
